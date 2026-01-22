import uuid
from typing import Annotated

from aiohttp import ClientSession
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Form,
    HTTPException,
    Request,
    Security,
)
from sqlmodel import Session

from app.internal.audiobookshelf.client import background_abs_trigger_scan
from app.internal.audiobookshelf.config import abs_config
from app.internal.auth.authentication import ABRAuth, DetailedUser
from app.internal.db_queries import (
    get_all_manual_requests,
    get_wishlist_counts,
    get_wishlist_results,
)
from app.internal.models import GroupEnum, AudiobookRequest, Audiobook
from app.routers.api.requests import (
    DownloadSourceBody,
    delete_manual_request,
    mark_manual_downloaded,
    start_auto_download_endpoint,
)
from app.routers.api.requests import download_book as api_download_book
from app.routers.api.requests import list_sources as api_list_sources
from app.routers.api.requests import mark_downloaded as api_mark_downloaded
from app.util.connection import get_connection
from app.util.db import get_session
from app.util.redirect import BaseUrlRedirectResponse
from app.util.templates import template_response
from app.util.toast import ToastException

router = APIRouter(prefix="/wishlist")


@router.get("/active-downloads")
async def active_downloads(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(ABRAuth())],
):
    from app.internal.download_clients.qbittorrent import QbittorrentClient
    from app.internal.download_clients.config import download_client_config
    from app.internal.models import AudiobookRequest, Audiobook
    from sqlmodel import select, or_, not_, col
    
    if not download_client_config.get_qbit_enabled(session):
        return ""
    
    # Fetch relevant requests (Downloading or Processing)
    # We want requests that are NOT fully downloaded yet
    query = select(AudiobookRequest, Audiobook).join(Audiobook).where(
        Audiobook.downloaded == False,
        or_(
            AudiobookRequest.torrent_hash != None,
            AudiobookRequest.processing_status != "pending"
        ),
        not_(col(AudiobookRequest.processing_status).startswith("failed"))
    )
    
    results = session.exec(query).all()
    
    if not results:
        return ""

    # Fetch active torrents for real-time speed/eta
    client = QbittorrentClient(session)
    category = download_client_config.get_qbit_category(session)
    try:
        # We fetch 'all' because 'active' might exclude paused/queued items that are technically still 'in progress' from our perspective
        # but filter='active' is usually what we want for speed/eta. 
        # Let's stick to 'active' for the enrichment data, but rely on DB for existence.
        torrents = await client.get_torrents(category=category, filter="active")
        torrents_by_hash = {t.get("hash"): t for t in torrents}
    except Exception:
        torrents_by_hash = {}
    
    downloads = []
    for req, book in results:
        # Match with torrent data
        t_data = torrents_by_hash.get(req.torrent_hash)
        
        item = {
            "title": book.title,
            "asin": book.asin,
            "cover": book.cover_image,
            "progress": req.download_progress or 0.0,
            "state": req.download_state,
            "processing_status": req.processing_status,
            "speed": 0,
            "eta": 0,
            "hash": req.torrent_hash
        }
        
        if t_data:
            item["progress"] = t_data.get("progress", 0)
            item["state"] = t_data.get("state", "unknown")
            item["speed"] = t_data.get("dlspeed", 0)
            item["eta"] = t_data.get("eta", 0)
        
        # Display Logic Cleanup
        display_state = item["state"]
        
        # If we are in a post-processing state, show that instead of torrent state
        if req.processing_status not in ["pending", "completed", "failed", "download_initiated"]:
             display_state = req.processing_status.replace("_", " ").title()
        
        item["display_state"] = display_state
        downloads.append(item)
    
    return template_response(
        "wishlist_page/active_downloads.html",
        request,
        user,
        {"downloads": downloads},
    )

@router.get("")
async def wishlist(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(ABRAuth())],
):
    username = None if user.is_admin() else user.username
    results = get_wishlist_results(session, username, "not_downloaded")
    counts = get_wishlist_counts(session, user)
    return template_response(
        "wishlist_page/wishlist.html",
        request,
        user,
        {"results": results, "page": "wishlist", "counts": counts},
    )


@router.get("/downloaded")
async def downloaded(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(ABRAuth())],
):
    username = None if user.is_admin() else user.username
    results = get_wishlist_results(session, username, "downloaded")
    counts = get_wishlist_counts(session, user)
    return template_response(
        "wishlist_page/wishlist.html",
        request,
        user,
        {"results": results, "page": "downloaded", "counts": counts},
    )

@router.get("/downloading")
async def downloading(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(ABRAuth())],
):
    from app.internal.models import AudiobookRequest
    from sqlmodel import select, or_, not_, col
    
    username = None if user.is_admin() else user.username
    
    # Fetch requests that are not downloaded and have a torrent_hash or are processing
    # AND are not in a failed state
    query = select(AudiobookRequest).join(Audiobook).where(
        Audiobook.downloaded == False, # Correctly check Audiobook.downloaded
        or_(
            AudiobookRequest.torrent_hash != None,
            AudiobookRequest.processing_status != "pending"
        ),
        not_(col(AudiobookRequest.processing_status).startswith("failed"))
    )
    if username:
        query = query.where(AudiobookRequest.user_username == username)
    
    downloading_requests = session.exec(query).all()
    
    # We need to transform these into a format similar to AudiobookWishlistResult
    # For now, let's just pass the raw AudiobookRequest objects,
    # we can refine this later if needed for consistent display with wishlist.html
    
    counts = get_wishlist_counts(session, user)
    return template_response(
        "wishlist_page/downloading.html",
        request,
        user,
        {"requests": downloading_requests, "page": "downloading", "counts": counts},
    )


@router.patch("/downloaded/{asin}")
async def update_downloaded(
    request: Request,
    asin: str,
    session: Annotated[Session, Depends(get_session)],
    background_task: BackgroundTasks,
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    await api_mark_downloaded(asin, session, background_task, admin_user)

    username = None if admin_user.is_admin() else admin_user.username
    results = get_wishlist_results(session, username, "not_downloaded")
    counts = get_wishlist_counts(session, admin_user)

    if abs_config.is_valid(session):
        background_task.add_task(background_abs_trigger_scan)

    return template_response(
        "wishlist_page/wishlist.html",
        request,
        admin_user,
        {
            "results": results,
            "page": "wishlist",
            "counts": counts,
            "update_tablist": True,
        },
        block_name="book_wishlist",
    )


@router.post("/reprocess/{asin}")
async def reprocess_book(
    asin: str,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    from app.internal.download_clients.qbittorrent import QbittorrentClient
    from app.internal.download_clients.config import download_client_config
    from app.internal.processing.processor import process_completed_download
    
    client = QbittorrentClient(session)
    # Search all torrents for this ASIN tag
    torrents = await client.get_torrents()
    
    matching_torrent = None
    for t in torrents:
        if f"asin:{asin}" in t.get("tags", ""):
            matching_torrent = t
            break
            
    if not matching_torrent:
        raise ToastException("Could not find a matching torrent in qBittorrent for this ASIN.", "error")
        
    download_path = matching_torrent.get("content_path")
    if not download_path:
        raise ToastException("Torrent found but content path is missing.", "error")
        
    try:
        await process_completed_download(session, asin, download_path)
        return template_response(
            "scripts/toast.html",
            None,
            None,
            {"message": "Reprocessing complete!", "type": "success"},
        )
    except Exception as e:
        raise ToastException(f"Reprocessing failed: {str(e)}", "error")

@router.get("/manual")
async def manual(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(ABRAuth())],
):
    books = get_all_manual_requests(session, user)
    counts = get_wishlist_counts(session, user)
    return template_response(
        "wishlist_page/manual.html",
        request,
        user,
        {"books": books, "page": "manual", "counts": counts},
    )


@router.patch("/manual/{id}")
async def downloaded_manual(
    request: Request,
    id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    background_task: BackgroundTasks,
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    await mark_manual_downloaded(id, session, background_task, admin_user)

    books = get_all_manual_requests(session, admin_user)
    counts = get_wishlist_counts(session, admin_user)

    if abs_config.is_valid(session):
        background_task.add_task(background_abs_trigger_scan)

    return template_response(
        "wishlist_page/manual.html",
        request,
        admin_user,
        {
            "books": books,
            "page": "manual",
            "counts": counts,
            "update_tablist": True,
        },
        block_name="book_wishlist",
    )


@router.delete("/manual/{id}")
async def delete_manual(
    request: Request,
    id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    await delete_manual_request(id, session, admin_user)

    books = get_all_manual_requests(session, admin_user)
    counts = get_wishlist_counts(session, admin_user)

    return template_response(
        "wishlist_page/manual.html",
        request,
        admin_user,
        {
            "books": books,
            "page": "manual",
            "counts": counts,
            "update_tablist": True,
        },
        block_name="book_wishlist",
    )


@router.get("/sources/{asin}")
async def list_sources(
    request: Request,
    asin: str,
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
    only_body: bool = False,
):
    try:
        result = await api_list_sources(
            asin,
            session,
            client_session,
            admin_user,
            only_cached=not only_body,
        )
    except HTTPException as e:
        if e.detail == "Prowlarr misconfigured":
            return BaseUrlRedirectResponse(
                "/settings/prowlarr?prowlarr_misconfigured=1", status_code=302
            )
        raise e

    if only_body:
        return template_response(
            "wishlist_page/sources.html",
            request,
            admin_user,
            {"result": result},
            block_name="body",
        )
    return template_response(
        "wishlist_page/sources.html",
        request,
        admin_user,
        {"result": result},
    )


@router.post("/sources/{asin}")
async def download_book(
    background_task: BackgroundTasks,
    asin: str,
    guid: Annotated[str, Form()],
    indexer_id: Annotated[int, Form()],
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    body = DownloadSourceBody(guid=guid, indexer_id=indexer_id)
    return await api_download_book(
        background_task=background_task,
        asin=asin,
        body=body,
        session=session,
        client_session=client_session,
        admin_user=admin_user,
    )


@router.post("/auto-download/{asin}")
async def start_auto_download(
    request: Request,
    asin: str,
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.trusted))],
):
    try:
        await start_auto_download_endpoint(asin, session, client_session, user)
    except HTTPException as e:
        raise ToastException(e.detail) from None

    username = None if user.is_admin() else user.username
    results = get_wishlist_results(session, username, "not_downloaded")
    counts = get_wishlist_counts(session, user)

    return template_response(
        "wishlist_page/wishlist.html",
        request,
        user,
        {
            "results": results,
            "page": "wishlist",
            "counts": counts,
            "update_tablist": True,
        },
        block_name="book_wishlist",
    )
