import os
import re
from typing import Optional
from aiohttp import ClientSession
from sqlmodel import Session
from app.internal.book_search import get_book_by_asin, store_new_books
from app.internal.metadata import generate_abs_metadata, generate_opf_metadata
from app.internal.media_management.config import media_management_config
from app.internal.models import Audiobook
from app.util.log import logger
from app.internal.library.scanner import LibraryScanner

def sanitize_filename(s: str) -> str:
    """
    Sanitizes a string for use as a filename or folder name.
    """
    if not s:
        return "Unknown"
    s = re.sub(r'[\\/*?:">|<]', "", s).strip()
    return s or "Unknown"


def _get_series_parts(book: Audiobook) -> tuple[str | None, str | None]:
    series_name = book.series[0] if book.series else None
    series_index = book.series_index
    if series_name and not series_index and " #" in series_name:
        base, idx = series_name.split(" #", 1)
        series_name = base.strip()
        series_index = idx.strip() or None
    return series_name, series_index

def get_book_folder_path(session: Session, book: Audiobook) -> Optional[str]:
    """
    Calculates the relative path for a book based on current patterns.
    """
    lib_root = media_management_config.get_library_path(session)
    if not lib_root:
        return None

    pattern = media_management_config.get_folder_pattern(session)
    author = book.authors[0] if book.authors else "Unknown"
    series, series_index = _get_series_parts(book)
    year = book.release_date.year if book.release_date else "Unknown"
    series_display = (
        f"{series} #{series_index}" if series and series_index else series
    )

    try:
        folder_rel_path = pattern.format(
            author=sanitize_filename(author),
            title=sanitize_filename(book.title),
            year=year,
            asin=book.asin,
            series=sanitize_filename(series_display) if series_display else "No Series",
            series_index=series_index or "",
        )
    except Exception as e:
        logger.warning("Pattern formatting failed, using default", error=str(e))
        folder_rel_path = f"{sanitize_filename(author)}/{sanitize_filename(book.title)} ({year})"

    if (
        media_management_config.get_use_series_folders(session)
        and series
        and "{series}" not in pattern
    ):
        folder_rel_path = os.path.join(
            sanitize_filename(author),
            sanitize_filename(series_display),
            sanitize_filename(book.title),
        )

    return folder_rel_path.strip().lstrip(os.path.sep)


def generate_audiobook_filename(
    book: Audiobook, file_pattern: str, part_str: str, ext: str
) -> str:
    author = book.authors[0] if book.authors else "Unknown"
    series, series_index = _get_series_parts(book)
    year = book.release_date.year if book.release_date else "Unknown"
    series_display = (
        f"{series} #{series_index}" if series and series_index else series
    )

    try:
        new_filename = file_pattern.format(
            author=sanitize_filename(author),
            title=sanitize_filename(book.title),
            year=year,
            asin=book.asin,
            series=sanitize_filename(series_display) if series_display else "No Series",
            series_index=series_index or "",
            part=part_str,
        ).strip()
        new_filename = re.sub(r"[\\s\\-\\._]+$", "", new_filename)
        if part_str and "{part}" not in file_pattern:
            new_filename += f" - {part_str}"
        new_filename += ext
    except Exception:
        new_filename = f"{sanitize_filename(book.title)}{' - ' + part_str if part_str else ''}{ext}"
    return new_filename


async def refresh_book_metadata(
    session: Session, asin: str, client_session: ClientSession
):
    """
    Refreshes metadata for a single book from the internet and updates DB/files.
    """
    # 1. Fetch from internet
    new_book_data = await get_book_by_asin(client_session, asin)
    if not new_book_data:
        logger.warning("Metadata refresh failed: Book not found on Audible", asin=asin)
        return

    # 2. Update DB
    store_new_books(session, [new_book_data])

    # 3. Update files on disk if it's already downloaded
    book = session.get(Audiobook, asin)
    if book and book.downloaded:
        lib_root = media_management_config.get_library_path(session)
        folder_rel_path = get_book_folder_path(session, book)
        
        if lib_root and folder_rel_path:
            dest_path = os.path.join(lib_root, folder_rel_path)

            if os.path.exists(dest_path):
                logger.info("Refreshing metadata files on disk", path=dest_path)
                await generate_abs_metadata(book, dest_path)
                await generate_opf_metadata(session, book, dest_path)


def library_contains_asin(session: Session, asin: str) -> bool:
    lib_root = media_management_config.get_library_path(session)
    if not lib_root:
        return False
    if not os.path.isdir(lib_root):
        return False
    return bool(LibraryScanner.find_book_path_by_asin(lib_root, asin))
