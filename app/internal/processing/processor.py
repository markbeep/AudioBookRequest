import os
import shutil
import re
from typing import Optional
from sqlmodel import Session
from app.internal.models import Audiobook, AudiobookRequest
from app.internal.media_management.config import media_management_config
from app.util.log import logger
from app.internal.metadata import generate_abs_metadata, generate_opf_metadata

def smart_copy(src: str, dst: str, use_hardlinks: bool = False, delete_source: bool = False):
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
            logger.debug("Processor: Hardlink failed, falling back to copy", error=str(e))

    shutil.copy2(src, dst)
    if delete_source:
        os.remove(src)

async def process_completed_download(session: Session, book_request: AudiobookRequest, download_path: str, delete_source: bool = False):
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

    pattern = media_management_config.get_folder_pattern(session)
    author = book.authors[0] if book.authors else "Unknown"
    series = book.series[0] if book.series else None
    year = book.release_date.year if book.release_date else "Unknown"

    # Sanitize for filesystem
    def sanitize(s: str) -> str:
        # Remove invalid characters and strip whitespace
        s = re.sub(r'[\\/*?:">|<]', "", s).strip()
        return s or "Unknown"

    # Construct relative path
    try:
        folder_rel_path = pattern.format(
            author=sanitize(author),
            title=sanitize(book.title),
            year=year,
            asin=book.asin,
            series=sanitize(series) if series else "No Series",
            series_index=book.series[0] if book.series else "" # Added generic support if pattern uses it
        )
    except Exception as e:
        logger.warning("Processor: Pattern formatting failed, using default", error=str(e))
        folder_rel_path = f"{sanitize(author)}/{sanitize(book.title)} ({year})"

    # Handle multiple series tags or nested series folders override
    if media_management_config.get_use_series_folders(session) and series and "{series}" not in pattern:
        folder_rel_path = os.path.join(sanitize(author), sanitize(series), sanitize(book.title))

    # Clean up the relative path (remove leading/trailing slashes/spaces)
    folder_rel_path = folder_rel_path.strip().lstrip(os.path.sep)
    if folder_rel_path.startswith("/"): # Double check for unix root
        folder_rel_path = folder_rel_path[1:]
    
    # Ensure we don't end up with empty segments if something was just a slash
    if not folder_rel_path:
        folder_rel_path = f"{sanitize(author)}/{sanitize(book.title)}"

    dest_path = os.path.join(lib_root, folder_rel_path)
    os.makedirs(dest_path, exist_ok=True)

    # 2. Organize files
    use_hardlinks = media_management_config.get_use_hardlinks(session)
    logger.info("Processor: Organizing and renaming files", dest=dest_path, hardlinks=use_hardlinks)

    source_paths = download_path.split("|")
    
    # Standardize filenames
    audio_files_to_process = []
    if len(source_paths) == 1 and os.path.isdir(source_paths[0]):
        # It's a directory. Find all audio files.
        for root, dirs, files in os.walk(source_paths[0]):
            for file in files:
                if any(file.lower().endswith(ext) for ext in [".m4b", ".mp3", ".m4a", ".flac", ".wav", ".ogg", ".opus", ".aac", ".wma"]):
                    audio_files_to_process.append(os.path.join(root, file))
        audio_files_to_process.sort()
    else:
        # It's a list of files or a single file
        audio_files_to_process = [p for p in source_paths if os.path.exists(p) and not os.path.isdir(p)]

    # Copy and Rename
    for idx, s_path in enumerate(audio_files_to_process, 1):
        ext = os.path.splitext(s_path)[1].lower()
        if len(audio_files_to_process) > 1:
            # Multi-part naming
            new_filename = f"{sanitize(book.title)} - Part {idx:02d}{ext}"
        else:
            # Single-file naming
            new_filename = f"{sanitize(book.title)}{ext}"
        
        d_path = os.path.join(dest_path, new_filename)
        smart_copy(s_path, d_path, use_hardlinks, delete_source)

    logger.info("Processor: Finished organizing and renaming all source files", count=len(audio_files_to_process))

    # Mark as downloaded so it appears in the library
    book.downloaded = True
    session.add(book)
    session.commit()

    book_request.processing_status = "generating_metadata"
    session.add(book_request)
    session.commit()
    logger.info("Processor: Setting status to generating_metadata", title=book.title)

    # 3. Generate Metadata Files (JSON and OPF)
    mam_result = None
    if book_request.mam_id:
        try:
            from app.internal.indexers.mam import fetch_mam_book_details, MamIndexer, ValuedMamConfigurations, SessionContainer
            from app.internal.indexers.configuration import create_valued_configuration
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
                    container=SessionContainer(session=session, client_session=client_session),
                    configurations=mam_config,
                    mam_id=book_request.mam_id
                )
        except Exception as e:
            logger.warning("Processor: Failed to fetch MAM details for metadata", error=str(e))

    logger.info("Processor: Generating Audiobookshelf metadata", title=book.title, path=dest_path)
    await generate_abs_metadata(book, dest_path, mam_result)
    logger.info("Processor: Generating OPF metadata", title=book.title, path=dest_path)
    await generate_opf_metadata(session, book, dest_path, mam_result)
    
    # 4. Save Cover (if available)
    if book.cover_image:
        try:
            import aiohttp
            async with aiohttp.ClientSession() as client_session:
                async with client_session.get(book.cover_image) as resp:
                    if resp.status == 200:
                        content = await resp.read()
                        cover_ext = os.path.splitext(book.cover_image.split('?')[0])[1] or ".jpg"
                        # Standard ABS cover name
                        cover_path = os.path.join(dest_path, f"cover{cover_ext}")
                        with open(cover_path, "wb") as f:
                            f.write(content)
                        logger.info("Processor: Saved cover art", path=cover_path)
        except Exception as e:
            logger.warning("Processor: Failed to save cover art", error=str(e))

    book_request.processing_status = "completed"
    session.add(book_request)
    session.commit()
    logger.info("Processor: Processing complete", title=book.title)