import asyncio
from app.util.log import logger
from app.internal.download_clients.qbittorrent import QbittorrentClient
from app.internal.download_clients.config import download_client_config
from app.internal.processing.processor import process_completed_download
from app.util.db import get_session
from app.internal.audiobookshelf.client import background_abs_trigger_scan

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
        
        await asyncio.sleep(60) # Check every minute

async def check_qbittorrent(session):
    client = QbittorrentClient(session)
    category = download_client_config.get_qbit_category(session)
    # Filter for completed (downloaded) torrents
    torrents = await client.get_torrents(category=category, filter="completed")
    
    any_processed = False
    for torrent in torrents:
        tags = torrent.get("tags", "")
        if "processed" in tags:
            continue
            
        asin = None
        if "asin:" in tags:
            # Extract ASIN from tags (e.g., "asin:B000000000")
            for tag in tags.split(","):
                tag = tag.strip()
                if tag.startswith("asin:"):
                    asin = tag.split(":", 1)[1]
                    break
        
        if asin:
            download_path = torrent.get("content_path")
            if download_path:
                logger.info("Monitor: Found completed download for ASIN", asin=asin, name=torrent.get("name"))
                try:
                    await process_completed_download(session, asin, download_path)
                    await client.add_torrent_tags(torrent.get("hash"), ["processed"])
                    any_processed = True
                except Exception as e:
                    logger.error("Monitor: Failed to process download", asin=asin, error=str(e))
    
    if any_processed:
        await background_abs_trigger_scan()

async def start_monitor():
    asyncio.create_task(download_monitor_loop())
