import asyncio
from sqlmodel import Session, select
from app.util.log import logger
from app.internal.download_clients.qbittorrent import QbittorrentClient
from app.internal.download_clients.config import download_client_config
from app.internal.processing.processor import process_completed_download
from app.util.db import get_session
from app.internal.audiobookshelf.client import background_abs_trigger_scan
from app.internal.models import AudiobookRequest, Audiobook # Import Audiobook


async def download_monitor_loop():
    """
    Background loop to monitor download clients for completed downloads.
    """
    logger.info("Monitor: Starting download monitor loop")
    while True:
        try:
            with next(get_session()) as session:
                if download_client_config.get_qbit_enabled(session):
                    await check_qbittorrent(session)
        except Exception as e:
            logger.error("Monitor: Error in monitor loop", error=str(e))
        
        await asyncio.sleep(10) # Check more frequently for better responsiveness (e.g., every 10 seconds)

async def check_qbittorrent(session: Session):
    client = QbittorrentClient(session)
    category = download_client_config.get_qbit_category(session)
    
    # Get all torrents to accurately reflect current download states
    all_torrents = await client.get_torrents(category=category)
    torrents_by_hash = {t.get("hash"): t for t in all_torrents}
    
    # Get all AudiobookRequests that are NOT yet fully downloaded and processed
    # and have an associated torrent or are in active processing
    requests_to_monitor = session.exec(
        select(AudiobookRequest).join(Audiobook).where(
            Audiobook.downloaded == False,
            (AudiobookRequest.torrent_hash != None) | (AudiobookRequest.processing_status != "pending")
        )
    ).all()
    
    any_processed = False
    for req in requests_to_monitor:
        asin = req.asin
        current_torrent = None
        
        # Try to find associated torrent
        if req.torrent_hash:
            current_torrent = torrents_by_hash.get(req.torrent_hash)
        
        # Fallback: If not found by hash (or no hash), try to find by ASIN tag
        if not current_torrent:
            for torrent in all_torrents:
                tags = torrent.get("tags", "")
                if f"asin:{asin}" in tags:
                    current_torrent = torrent
                    # Self-heal: Update the hash in DB to match the actual active torrent
                    if req.torrent_hash != torrent.get("hash"):
                        logger.info("Monitor: Updating torrent hash from tag match", asin=asin, old_hash=req.torrent_hash, new_hash=torrent.get("hash"))
                        req.torrent_hash = torrent.get("hash")
                        session.add(req)
                    break

        if current_torrent:
            # Update download status from qBittorrent
            req.download_progress = current_torrent.get("progress", 0.0)
            req.download_state = current_torrent.get("state", "unknown")
            session.add(req)
            
            # If download is complete and not yet processed
            if req.download_progress >= 1.0 and req.processing_status not in ["completed", "failed", "queued"]:
                logger.info("Monitor: Found completed download for ASIN, starting processing", asin=asin, name=current_torrent.get("name"))
                download_path = current_torrent.get("content_path")
                if download_path:
                    try:
                        # Update processing status before calling
                        req.processing_status = "queued"
                        session.add(req)
                        session.commit() # Commit to make status visible
                        
                        await process_completed_download(session, req, download_path)
                        await client.add_torrent_tags(current_torrent.get("hash"), ["processed"])
                        any_processed = True
                        
                        req.processing_status = "completed"
                        # Mark the associated Audiobook as fully processed and downloaded
                        book_to_mark = session.exec(select(Audiobook).where(Audiobook.asin == req.asin)).first()
                        if book_to_mark:
                            book_to_mark.downloaded = True
                            session.add(book_to_mark)
                        # The AudiobookRequest itself does not have a 'downloaded' flag, the Audiobook does.
                        # We are relying on Audiobook.downloaded == False for the filtering in the UI.
                    except Exception as e:
                        logger.error("Monitor: Failed to process download", asin=asin, error=str(e))
                        req.processing_status = f"failed: {str(e)}"
                        session.add(req)
                else:
                    logger.warning("Monitor: Completed torrent has no content_path", asin=asin)
                    req.processing_status = "failed: no content path"
                    session.add(req)
        elif req.torrent_hash and not req.processing_status.startswith("failed") and req.processing_status != "completed":
            # Torrent hash exists, but no matching torrent found in qBittorrent (stale entry)
            logger.warning("Monitor: Stale entry detected, torrent missing in qBittorrent", asin=asin, torrent_hash=req.torrent_hash)
            req.download_state = "torrent_missing"
            req.processing_status = "failed: torrent missing"
            session.add(req)
        session.commit() # Commit changes for this request

    if any_processed:
        await background_abs_trigger_scan()

async def start_monitor():
    asyncio.create_task(download_monitor_loop())
