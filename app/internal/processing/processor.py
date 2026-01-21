import json
import os
import shutil
import re
from typing import Optional, List
from app.internal.models import Audiobook, AudiobookRequest
from app.util.log import logger
from app.internal.media_management.config import media_management_config
from sqlmodel import Session, select

async def process_completed_download(session: Session, asin: str, download_path: str):
    """
    Process a completed download:
    1. Move to the library path using the configured pattern.
    2. Generate metadata files (json, opf).
    3. Save cover image.
    4. Clean up.
    """
    book = session.get(Audiobook, asin)
    if not book:
        logger.error("Processor: Book not found in database", asin=asin)
        return

    logger.info("Processor: Starting processing for book", title=book.title, asin=asin)

    # 1. Determine destination path
    lib_root = media_management_config.get_library_path(session)
    if not lib_root:
        logger.warning("Processor: Library path not set, skipping move")
        return

    pattern = media_management_config.get_folder_pattern(session)
    
    # Simple replacement for pattern
    year = str(book.release_date.year) if book.release_date else "Unknown"
    author = book.authors[0] if book.authors else "Unknown Author"
    series = book.series[0] if book.series else ""
    
    # Sanitize for filesystem
    def sanitize(s: str) -> str:
        return re.sub(r'[\\/*?:">|<]', "", s).strip()

    folder_rel_path = pattern.format(
        author=sanitize(author),
        title=sanitize(book.title),
        year=year,
        asin=book.asin,
        series=sanitize(series) if series else "No Series"
    )
    
    # Handle multiple series tags or nested series folders
    if media_management_config.get_use_series_folders(session) and series and "{series}" not in pattern:
        folder_rel_path = os.path.join(sanitize(author), sanitize(series), sanitize(book.title))

    dest_path = os.path.join(lib_root, folder_rel_path)
    os.makedirs(dest_path, exist_ok=True)

    use_hardlinks = media_management_config.get_use_hardlinks(session)
    logger.info("Processor: Organizing files", dest=dest_path, hardlinks=use_hardlinks)

    def smart_copy(src, dst):
        if use_hardlinks:
            try:
                os.link(src, dst)
                return
            except OSError:
                # Fallback to copy if hardlink fails (e.g. cross-device)
                pass
        shutil.copy2(src, dst)

    # 2. Organize files
    if os.path.isdir(download_path):
        for root, dirs, files in os.walk(download_path):
            # Create subdirectories in destination
            rel_dir = os.path.relpath(root, download_path)
            if rel_dir != ".":
                os.makedirs(os.path.join(dest_path, rel_dir), exist_ok=True)
            
            for file in files:
                s = os.path.join(root, file)
                d = os.path.join(dest_path, rel_dir, file) if rel_dir != "." else os.path.join(dest_path, file)
                smart_copy(s, d)
    else:
        smart_copy(download_path, os.path.join(dest_path, os.path.basename(download_path)))

    # 3. Generate Metadata Files (JSON and OPF)
    # These are saved directly in the destination folder
    await generate_abs_metadata(book, dest_path)
    await generate_opf_metadata(session, book, dest_path)
    
    # 4. Save Cover (if available)
    if book.cover_image and not book.cover_image.startswith("http"):
        # If it's a local path or we can fetch it, save it as cover.jpg
        pass # Handle this if needed, ABS usually handles the cover if it finds metadata.json or cover.jpg
    
    logger.info("Processor: Finished processing and metadata generation", title=book.title)
    
    # Mark as downloaded in DB if not already
    book.downloaded = True
    session.add(book)
    session.commit()

async def generate_abs_metadata(book: Audiobook, folder_path: str):
    """Generates metadata.json in Audiobookshelf format"""
    metadata = {
        "title": book.title,
        "subtitle": book.subtitle,
        "authors": book.authors,
        "narrators": book.narrators,
        "series": book.series,
        "publishedYear": str(book.release_date.year) if book.release_date else None,
        "publishedDate": book.release_date.isoformat() if book.release_date else None,
        "asin": book.asin,
        # "description": "...", # Need to get this from somewhere
    }
    
    file_path = os.path.join(folder_path, "metadata.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=4)

async def generate_opf_metadata(session: Session, book: Audiobook, folder_path: str):
    """Generates metadata.opf. If MAM data exists, we try to use the more detailed generator."""
    from app.internal.metadata import generate_opf_for_mam
    from app.internal.indexers.mam import fetch_mam_book_details, MamIndexer, ValuedMamConfigurations, SessionContainer
    from app.internal.indexers.configuration import create_valued_configuration
    import aiohttp

    # Check if we have a MAM ID for this book
    request = session.exec(select(AudiobookRequest).where(AudiobookRequest.asin == book.asin)).first()
    
    if request and request.mam_id:
        try:
            async with aiohttp.ClientSession() as client_session:
                config_obj = await MamIndexer.get_configurations(
                    SessionContainer(session=session, client_session=client_session)
                )
                valued = create_valued_configuration(config_obj, session)
                mam_config = ValuedMamConfigurations(
                    mam_session_id=str(getattr(valued, "mam_session_id") or "")
                )
                
                details = await fetch_mam_book_details(
                    container=SessionContainer(session=session, client_session=client_session),
                    configurations=mam_config,
                    mam_id=request.mam_id
                )
                
                if details:
                    opf_content = generate_opf_for_mam(details)
                    with open(os.path.join(folder_path, "metadata.opf"), "w", encoding="utf-8") as f:
                        f.write(opf_content)
                    return
        except Exception as e:
            logger.error("Processor: Failed to fetch MAM details for OPF", error=str(e))

    # Fallback/Basic OPF if MAM not available or failed
    # (Simplified OPF generation)
    pass
