import os
import shutil
from typing import Optional
from sqlmodel import Session
from app.internal.models import Audiobook, AudiobookRequest
from app.internal.request_logs import log_request_event
from app.internal.media_management.config import media_management_config
from app.internal.library.service import (
    get_book_folder_path,
    generate_audiobook_filename,
)
from app.util.log import logger
from app.util.sort import natural_sort
from app.internal.metadata import generate_abs_metadata, generate_opf_metadata


def smart_copy(
    src: str, dst: str, use_hardlinks: bool = False, delete_source: bool = False
):
    """
    Copies (or hardlinks) a file to a new destination.
    If delete_source is True, it effectively 'moves' the file.
    """
    # Safety: Don't do anything if source and destination are the same
    if os.path.abspath(src) == os.path.abspath(dst):
        return

    os.makedirs(os.path.dirname(dst), exist_ok=True)

    if use_hardlinks:
        try:
            os.link(src, dst)
            if delete_source:
                os.remove(src)
            return
        except Exception as e:
            logger.debug(
                "Processor: Hardlink failed, falling back to copy", error=str(e)
            )

    shutil.copy2(src, dst)
    if delete_source:
        os.remove(src)


async def process_completed_download(
    session: Session,
    book_request: AudiobookRequest,
    download_path: str,
    delete_source: bool = False,
):
    """
    Takes a completed download, organizes it into the library, and generates metadata.
    """
    book = session.get(Audiobook, book_request.asin)
    if not book:
        logger.error("Processor: Book not found in database", asin=book_request.asin)
        return

    lib_root = media_management_config.get_library_path(session)
    if not lib_root:
        logger.error("Processor: Library path not configured")
        return

    author = book.authors[0] if book.authors else "Unknown"
    # series = book.series[0] if book.series else None
    year = book.release_date.year if book.release_date else "Unknown"

    folder_rel_path = get_book_folder_path(session, book)
    if not folder_rel_path:
        folder_rel_path = f"{author}/{book.title} ({year})"

    dest_path = os.path.join(lib_root, folder_rel_path)
    os.makedirs(dest_path, exist_ok=True)

    # 2. Organize files
    from app.internal.download_clients.config import download_client_config

    complete_action = download_client_config.get_qbit_complete_action(session)
    use_hardlinks = complete_action == "hardlink"
    delete_source = delete_source or complete_action == "move"
    file_pattern = media_management_config.get_file_pattern(session)
    logger.info(
        "Processor: Organizing and renaming files",
        dest=dest_path,
        hardlinks=use_hardlinks,
    )

    book_request.processing_status = "organizing_files"
    log_request_event(
        session,
        book_request.asin,
        book_request.user_username,
        "Organizing and renaming files.",
        commit=False,
    )
    session.add(book_request)
    session.commit()

    source_paths = download_path.split("|")
    audio_files_to_process = []
    if len(source_paths) == 1 and os.path.isdir(source_paths[0]):
        for root, dirs, files in os.walk(source_paths[0]):
            for file in files:
                if any(
                    file.lower().endswith(ext)
                    for ext in [
                        ".m4b",
                        ".mp3",
                        ".m4a",
                        ".flac",
                        ".wav",
                        ".ogg",
                        ".opus",
                        ".aac",
                        ".wma",
                    ]
                ):
                    audio_files_to_process.append(os.path.join(root, file))
        natural_sort(audio_files_to_process)
    else:
        audio_files_to_process = [
            p for p in source_paths if os.path.exists(p) and not os.path.isdir(p)
        ]

    mam_result = None
    if book_request.mam_id:
        try:
            from app.internal.indexers.mam import (
                fetch_mam_book_details,
                MamIndexer,
                ValuedMamConfigurations,
                SessionContainer,
            )
            from app.internal.indexers.configuration import create_valued_configuration
            from app.internal.book_search import _normalize_series
            import aiohttp

            async with aiohttp.ClientSession() as client_session:
                config_obj = await MamIndexer.get_configurations(
                    SessionContainer(session=session, client_session=client_session)
                )
                valued = create_valued_configuration(config_obj, session)
                mam_config = ValuedMamConfigurations(
                    mam_session_id=str(getattr(valued, "mam_session_id") or "")
                )
                mam_result = await fetch_mam_book_details(
                    container=SessionContainer(
                        session=session, client_session=client_session
                    ),
                    configurations=mam_config,
                    mam_id=book_request.mam_id,
                )

            if mam_result and not book.series_index:
                mam_series, mam_index = _normalize_series(mam_result.series)
                if mam_index:
                    book.series_index = mam_index
                if not book.series and mam_series:
                    book.series = mam_series
                session.add(book)
                session.commit()
        except Exception:
            pass

    # Copy and Rename
    padding = 3 if len(audio_files_to_process) >= 100 else 2
    total_files = len(audio_files_to_process)
    for idx, s_path in enumerate(audio_files_to_process, 1):
        ext = os.path.splitext(s_path)[1].lower()
        part_str = f"Part {idx:0{padding}d}" if total_files > 1 else ""

        new_filename = generate_audiobook_filename(book, file_pattern, part_str, ext)

        d_path = os.path.join(dest_path, new_filename)
        smart_copy(s_path, d_path, use_hardlinks, delete_source)

        # Update progress during copying (0.90 to 0.92)
        book_request.download_progress = 0.90 + (idx / total_files * 0.02)
        session.add(book_request)
        session.commit()

    book.downloaded = True
    session.add(book)
    session.commit()

    book_request.processing_status = "generating_metadata"
    book_request.download_progress = 0.95
    log_request_event(
        session,
        book_request.asin,
        book_request.user_username,
        "Generating metadata files.",
        commit=False,
    )
    session.add(book_request)
    session.commit()

    await generate_abs_metadata(book, dest_path, mam_result)
    await generate_opf_metadata(session, book, dest_path, mam_result)

    if book.cover_image:
        book_request.processing_status = "saving_cover"
        book_request.download_progress = 0.98
        log_request_event(
            session,
            book_request.asin,
            book_request.user_username,
            "Saving cover image.",
            commit=False,
        )
        session.add(book_request)
        session.commit()
        try:
            import aiohttp

            async with aiohttp.ClientSession() as client_session:
                async with client_session.get(book.cover_image) as resp:
                    if resp.status == 200:
                        content = await resp.read()
                        cover_ext = (
                            os.path.splitext(book.cover_image.split("?")[0])[1]
                            or ".jpg"
                        )
                        cover_path = os.path.join(dest_path, f"cover{cover_ext}")
                        with open(cover_path, "wb") as f:
                            f.write(content)
        except Exception:
            pass

    book_request.processing_status = "completed"
    book_request.download_progress = 1.0
    log_request_event(
        session,
        book_request.asin,
        book_request.user_username,
        "Import completed.",
        commit=False,
    )
    session.add(book_request)
    session.commit()


async def reorganize_existing_book(
    session: Session, book: Audiobook, current_path: Optional[str] = None
):
    """
    Finds a book on disk and re-organizes/re-names its files according to current patterns.
    """
    from app.internal.library.scanner import LibraryScanner

    lib_root = media_management_config.get_library_path(session)
    if not lib_root:
        return

    if not current_path:
        current_path = LibraryScanner.find_book_path_by_asin(lib_root, book.asin)

    if not current_path:
        return

    file_pattern = media_management_config.get_file_pattern(session)
    author = book.authors[0] if book.authors else "Unknown"
    # series = book.series[0] if book.series else None
    year = book.release_date.year if book.release_date else "Unknown"

    folder_rel_path = get_book_folder_path(session, book)
    if not folder_rel_path:
        folder_rel_path = f"{author}/{book.title} ({year})"

    dest_path = os.path.join(lib_root, folder_rel_path)

    if os.path.abspath(current_path) != os.path.abspath(dest_path):
        logger.info(
            "Processor: Moving book folder",
            title=book.title,
            old=current_path,
            new=dest_path,
        )
    else:
        logger.info(
            "Processor: Renaming files within folder", title=book.title, path=dest_path
        )

    audio_files = []
    for f in os.listdir(current_path):
        if any(
            f.lower().endswith(ext)
            for ext in [
                ".m4b",
                ".mp3",
                ".m4a",
                ".flac",
                ".wav",
                ".ogg",
                ".opus",
                ".aac",
                ".wma",
            ]
        ):
            audio_files.append(os.path.join(current_path, f))
    natural_sort(audio_files)
    if not audio_files:
        return

    os.makedirs(dest_path, exist_ok=True)
    new_audio_paths = []
    padding = 3 if len(audio_files) >= 100 else 2
    for idx, s_path in enumerate(audio_files, 1):
        ext = os.path.splitext(s_path)[1].lower()
        part_str = f"Part {idx:0{padding}d}" if len(audio_files) > 1 else ""
        
        new_filename = generate_audiobook_filename(book, file_pattern, part_str, ext)
        
        d_path = os.path.join(dest_path, new_filename)
        if os.path.abspath(s_path) != os.path.abspath(d_path):
            shutil.move(s_path, d_path)
        new_audio_paths.append(d_path)

    for f in os.listdir(current_path):
        s_path = os.path.join(current_path, f)
        if s_path in new_audio_paths or os.path.isdir(s_path):
            continue
        d_path = os.path.join(dest_path, f)
        if os.path.abspath(s_path) != os.path.abspath(d_path):
            shutil.move(s_path, d_path)

    try:
        if current_path != dest_path and not os.listdir(current_path):
            os.removedirs(current_path)
    except Exception:
        pass

    await generate_abs_metadata(book, dest_path)
    await generate_opf_metadata(session, book, dest_path)
