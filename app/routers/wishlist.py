import uuid
import re
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
        return template_response(
            "wishlist_page/active_downloads.html",
            request,
            user,
            {"downloads": []},
        )

    username = None if user.is_admin() else user.username

    # Fetch active torrents for real-time speed/eta
    client = QbittorrentClient(session)
    category = download_client_config.get_qbit_category(session)
    try:
        # Fetch all torrents in our category
        torrents = await client.get_torrents(category=category)
    except Exception:
        torrents = []

    # Map torrents to their ASINs using tags (e.g., "asin:B00..." tag)
    # This ensures we only show what is actually in the client
    downloads = []
    
    # Pre-fetch books for all these torrents to avoid N+1 queries
    all_asins = []
    for t in torrents:
        tags = t.get("tags", "")
        match = re.search(r"asin:([A-Z0-9]{10})", tags)
        if match:
            all_asins.append(match.group(1))
    
    # 1. Fetch books and requests already identified from qB
    books = {b.asin: b for b in session.exec(select(Audiobook).where(col(Audiobook.asin).in_(all_asins))).all()}
    requests = {r.asin: r for r in session.exec(select(AudiobookRequest).where(col(AudiobookRequest.asin).in_(all_asins))).all()}

    # 2. ALSO fetch items from DB that are actively being processed by Narrarr but NOT in qB
    # We only show items that are beyond 'pending' and 'download_initiated' 
    # (e.g. 'generating_metadata', 'organizing', etc.)
    db_downloading = session.exec(
        select(AudiobookRequest).join(Audiobook).where(
            Audiobook.downloaded == False,
            not_(col(AudiobookRequest.processing_status).in_(["pending", "download_initiated", "completed"])),
            not_(col(AudiobookRequest.processing_status).startswith("failed")),
            not_(col(AudiobookRequest.asin).in_(all_asins)), # Not already found in qB
            not username or AudiobookRequest.user_username == username,
        )
    ).all()

    # Add qB torrents to the list
    for t in torrents:
        tags = t.get("tags", "")
        match = re.search(r"asin:([A-Z0-9]{10})", tags)
        asin = match.group(1) if match else None
        
        book = books.get(asin) if asin else None
        req = requests.get(asin) if asin else None
        
        title = book.title if book else t.get("name")
        cover = book.cover_image if book else None
        
        processing_status = req.processing_status if req else "pending"
        is_processing = processing_status not in ["pending", "completed", "failed", "download_initiated"]
        
        display_state = t.get("state", "unknown")
        if is_processing:
             display_state = processing_status.replace("_", " ").title()

        downloads.append({
            "title": title,
            "asin": asin,
            "cover": cover,
            "progress": t.get("progress", 0),
            "state": t.get("state", "unknown"),
            "processing_status": processing_status,
            "speed": t.get("dlspeed", 0),
            "eta": t.get("eta", 0),
            "hash": t.get("hash"),
            "display_state": display_state
        })

    # Add DB-only processing items to the list
    for req in db_downloading:
        book = session.get(Audiobook, req.asin)
        if not book: continue
        
        downloads.append({
            "title": book.title,
            "asin": book.asin,
            "cover": book.cover_image,
            "progress": 1.0, # Usually finishing up if not in qB
            "state": "processing",
            "processing_status": req.processing_status,
            "speed": 0,
            "eta": 0,
            "hash": req.torrent_hash,
            "display_state": req.processing_status.replace("_", " ").title()
        })
    
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
    counts = get_wishlist_counts(session, user)
    return template_response(
        "wishlist_page/downloading.html",
        request,
        user,
        {"page": "downloading", "counts": counts},
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
