import json
import os
import shutil
import re
from typing import Optional, List
from app.internal.models import Audiobook, AudiobookRequest
from app.util.log import logger
from app.internal.media_management.config import media_management_config
from sqlmodel import Session, select

async def process_completed_download(session: Session, book_request: AudiobookRequest, download_path: str, delete_source: bool = False):
    """
    Process a completed download:
    1. Move to the library path using the configured pattern.
    2. Generate metadata files (json, opf).
    3. Save cover image.
    4. Clean up.
    """
    asin = book_request.asin
    book = session.get(Audiobook, asin)
    if not book:
        logger.error("Processor: Book not found in database", asin=asin)
        book_request.processing_status = "failed: book not found"
        session.add(book_request)
        session.commit()
        return

    logger.info("Processor: Starting processing for book", title=book.title, asin=asin)

    book_request.processing_status = "moving_files"
    session.add(book_request)
    session.commit()
    logger.info("Processor: Setting status to moving_files", title=book.title)

    # 1. Determine destination path
    lib_root = media_management_config.get_library_path(session)
    if not lib_root:
        logger.warning("Processor: Library path not set, skipping move")
        book_request.processing_status = "failed: library path not set"
        session.add(book_request)
        session.commit()
        return

    pattern = media_management_config.get_folder_pattern(session)
    
    # Simple replacement for pattern
    year = str(book.release_date.year) if book.release_date else "Unknown"
    author = book.authors[0] if book.authors else "Unknown Author"
    series = book.series[0] if book.series else ""
    
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

    use_hardlinks = media_management_config.get_use_hardlinks(session)
    logger.info("Processor: Organizing files", dest=dest_path, hardlinks=use_hardlinks)

    # 2. Organize files
    if os.path.isdir(download_path):
        logger.info("Processor: Moving directory contents", source=download_path, destination=dest_path)
        for root, dirs, files in os.walk(download_path):
            # Create subdirectories in destination
            rel_dir = os.path.relpath(root, download_path)
            if rel_dir != ".":
                os.makedirs(os.path.join(dest_path, rel_dir), exist_ok=True)
            
            for file in files:
                s = os.path.join(root, file)
                d = os.path.join(dest_path, rel_dir, file) if rel_dir != "." else os.path.join(dest_path, file)
                smart_copy(s, d, use_hardlinks, delete_source)
        logger.info("Processor: Finished moving directory contents", destination=dest_path)
    else:
        logger.info("Processor: Moving single file", source=download_path, destination=dest_path)
        smart_copy(download_path, os.path.join(dest_path, os.path.basename(download_path)), use_hardlinks, delete_source)
        logger.info("Processor: Finished moving single file", destination=dest_path)

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
        cover_path = os.path.join(dest_path, "cover.jpg")
        if book.cover_image.startswith("http"):
            try:
                import aiohttp
                async with aiohttp.ClientSession() as client_session:
                    async with client_session.get(book.cover_image) as resp:
                        if resp.status == 200:
                            content = await resp.read()
                            with open(cover_path, "wb") as f:
                                f.write(content)
                            logger.info("Processor: Downloaded cover image", url=book.cover_image)
                        else:
                            logger.warning("Processor: Failed to download cover", status=resp.status, url=book.cover_image)
            except Exception as e:
                logger.error("Processor: Failed to download cover", error=str(e))
        elif os.path.exists(book.cover_image):
             try:
                 shutil.copy2(book.cover_image, cover_path)
                 logger.info("Processor: Copied local cover image", source=book.cover_image)
             except Exception as e:
                 logger.error("Processor: Failed to copy local cover", error=str(e))
    
    logger.info("Processor: Finished processing and metadata generation", title=book.title)

def smart_copy(source: str, destination: str, use_hardlinks: bool = False, delete_source: bool = False):
    """
    Copies a file from source to destination. 
    If use_hardlinks is True, attempts to hardlink first, falling back to copy.
    If delete_source is True, removes the source file after successful copy/link.
    """
    if os.path.exists(destination):
        logger.debug("Processor: Destination exists, overwriting", path=destination)
        if os.path.isdir(destination):
            shutil.rmtree(destination)
        else:
            os.remove(destination)
        
    success = False
    if use_hardlinks:
        try:
            os.link(source, destination)
            logger.debug("Processor: Hardlinked file", source=source, dest=destination)
            success = True
        except OSError as e:
            logger.warning("Processor: Hardlink failed, falling back to copy", error=str(e))
    
    if not success:
        try:
            shutil.copy2(source, destination)
            logger.debug("Processor: Copied file", source=source, dest=destination)
            success = True
        except Exception as e:
            logger.error("Processor: Copy failed", source=source, dest=destination, error=str(e))
            raise e
            
    if success and delete_source:
        try:
            os.remove(source)
            logger.debug("Processor: Deleted source file after move", source=source)
        except Exception as e:
            logger.warning("Processor: Failed to delete source file", source=source, error=str(e))



async def generate_abs_metadata(book: Audiobook, folder_path: str, mam_result: Optional["_Result"] = None):
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
    }
    
    if mam_result:
        if mam_result.synopsis:
            metadata["description"] = re.sub(r'<[^<]+?>', '', mam_result.synopsis).strip()
        if mam_result.tags:
            tags = [t.strip() for t in mam_result.tags.split(',') if t.strip()]
            metadata["tags"] = tags
            metadata["genres"] = tags
        if mam_result.languages:
            metadata["language"] = mam_result.languages[0]
        if mam_result.series:
            metadata["series"] = mam_result.series

    file_path = os.path.join(folder_path, "metadata.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=4)

async def generate_opf_metadata(session: Session, book: Audiobook, folder_path: str, mam_result: Optional["_Result"] = None):
    """Generates metadata.opf. If MAM data exists, we try to use the more detailed generator."""
    from app.internal.metadata import generate_opf_for_mam, generate_opf_basic

    if mam_result:
        try:
            opf_content = generate_opf_for_mam(mam_result)
            with open(os.path.join(folder_path, "metadata.opf"), "w", encoding="utf-8") as f:
                f.write(opf_content)
            return
        except Exception as e:
            logger.error("Processor: Failed to generate MAM OPF", error=str(e))

    # Fallback/Basic OPF if MAM not available or failed
    try:
        opf_content = generate_opf_basic(book)
        with open(os.path.join(folder_path, "metadata.opf"), "w", encoding="utf-8") as f:
            f.write(opf_content)
        logger.info("Processor: Generated basic OPF metadata", title=book.title)
    except Exception as e:
        logger.error("Processor: Failed to generate basic OPF metadata", error=str(e))
