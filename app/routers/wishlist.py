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
    Query,
    Request,
    Security,
)
from sqlmodel import Session, select

from app.internal.audiobookshelf.client import background_abs_trigger_scan
from app.internal.audiobookshelf.config import abs_config
from app.internal.auth.authentication import ABRAuth, DetailedUser
from app.internal.db_queries import (
    get_all_manual_requests,
    get_wishlist_counts,
    get_wishlist_results,
)
from app.internal.models import (
    GroupEnum,
    AudiobookRequest,
    Audiobook,
    User,
    AudiobookWishlistResult,
)
from app.internal.query import background_start_query
from app.internal.request_logs import get_request_logs, log_request_event
from app.routers.api.requests import (
    DownloadSourceBody,
    delete_manual_request,
    mark_manual_downloaded,
    start_auto_download_endpoint,
)
from app.routers.api.requests import download_book as api_download_book
from app.routers.api.requests import delete_request as api_delete_request
from app.routers.api.requests import list_sources as api_list_sources
from app.routers.api.requests import mark_downloaded as api_mark_downloaded
from app.util.connection import get_connection
from app.util.db import get_session
from app.util.redirect import BaseUrlRedirectResponse
from app.util.templates import template_response
from app.util.toast import ToastException

router = APIRouter(prefix="/wishlist")


def _status_stage(processing_status: str, progress: float) -> tuple[int, str]:
    if processing_status.startswith("failed"):
        return 2, "Failed"
    if processing_status == "completed":
        return 3, "Completed"
    if processing_status == "review_required":
        return 2, "Review Required"
    if processing_status in [
        "queued",
        "organizing_files",
        "generating_metadata",
        "saving_cover",
    ]:
        return 2, "Processing"
    if processing_status == "download_initiated" or progress > 0:
        return 1, "Downloading"
    return 0, "Requested"


def _build_attention_results(
    session: Session,
    username: str | None,
    filters: list[str] | None = None,
) -> tuple[list[AudiobookWishlistResult], dict[str, list[str]]]:
    results = get_wishlist_results(session, username, "all")
    issue_map: dict[str, list[str]] = {}
    filtered: list[AudiobookWishlistResult] = []

    for result in results:
        book = result.book
        if book.downloaded:
            continue

        issues: set[str] = set()
        if not book.cover_image:
            issues.add("missing_cover")

        requests = (
            result.requests
            if username is None
            else [req for req in result.requests if req.user_username == username]
        )
        for req in requests:
            if req.processing_status.startswith("failed"):
                issues.add("failed")
            if req.processing_status == "review_required":
                issues.add("review")

        if not issues:
            continue
        if filters and not issues.intersection(filters):
            continue

        issue_map[book.asin] = sorted(issues)
        filtered.append(result)

    return filtered, issue_map


def _render_wishlist_page(
    request: Request,
    session: Session,
    user: DetailedUser,
    page: str,
):
    username = None if user.is_admin() else user.username
    response_type = "downloaded" if page == "downloaded" else "not_downloaded"
    results = get_wishlist_results(session, username, response_type)
    counts = get_wishlist_counts(session, user)
    return template_response(
        "wishlist_page/wishlist.html",
        request,
        user,
        {
            "results": results,
            "page": page,
            "counts": counts,
            "update_tablist": True,
        },
        block_name="book_wishlist",
    )


@router.get("/active-downloads")
async def active_downloads(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(ABRAuth())],
):
    from app.internal.download_clients.qbittorrent import QbittorrentClient
    from app.internal.download_clients.config import download_client_config
    from sqlmodel import select, not_, col

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
    books = {
        b.asin: b
        for b in session.exec(
            select(Audiobook).where(col(Audiobook.asin).in_(all_asins))
        ).all()
    }
    requests = {
        r.asin: r
        for r in session.exec(
            select(AudiobookRequest).where(col(AudiobookRequest.asin).in_(all_asins))
        ).all()
    }

    # 2. ALSO fetch items from DB that are actively being processed by Narrarr but NOT in qB
    # We only show items that are beyond 'pending' and 'download_initiated'
    # (e.g. 'generating_metadata', 'organizing', etc.)
    db_downloading = session.exec(
        select(AudiobookRequest)
        .join(Audiobook)
        .where(
            not_(Audiobook.downloaded),
            not_(
                col(AudiobookRequest.processing_status).in_(
                    ["pending", "download_initiated", "completed"]
                )
            ),
            not_(col(AudiobookRequest.processing_status).startswith("failed")),
            not_(col(AudiobookRequest.asin).in_(all_asins)),  # Not already found in qB
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

        # Guard: If request is marked completed in DB, skip showing it in downloading tab
        if req and req.processing_status == "completed":
            continue

        title = book.title if book else t.get("name")
        cover = book.cover_image if book else None

        processing_status = req.processing_status if req else "pending"
        is_processing = processing_status not in [
            "pending",
            "completed",
            "failed",
            "download_initiated",
        ]

        display_state = t.get("state", "unknown")
        if is_processing:
            display_state = processing_status.replace("_", " ").title()

        progress_value = req.download_progress if req else t.get("progress", 0)
        stage, stage_label = _status_stage(processing_status, progress_value)
        error_reason = None
        if processing_status.startswith("failed:"):
            error_reason = processing_status.split(":", 1)[1].strip()
        logs = []
        if req:
            logs = [
                {
                    "message": log.message,
                    "level": log.level.value,
                    "timestamp": log.created_at.strftime("%b %d %H:%M"),
                }
                for log in get_request_logs(
                    session,
                    req.asin,
                    None if user.is_admin() else user.username,
                )
            ]

        downloads.append(
            {
                "title": title,
                "asin": asin,
                "cover": cover,
                "progress": progress_value,
                "state": t.get("state", "unknown"),
                "processing_status": processing_status,
                "speed": t.get("dlspeed", 0),
                "eta": t.get("eta", 0),
                "hash": t.get("hash"),
                "display_state": display_state,
                "stage": stage,
                "stage_label": stage_label,
                "error_reason": error_reason,
                "logs": logs,
            }
        )

    # Add DB-only processing items to the list
    for req in db_downloading:
        book = session.get(Audiobook, req.asin)
        if not book:
            continue

        downloads.append(
            {
                "title": book.title,
                "asin": book.asin,
                "cover": book.cover_image,
                "progress": req.download_progress,  # Use the progress from the database
                "state": "processing",
                "processing_status": req.processing_status,
                "speed": 0,
                "eta": 0,
                "hash": req.torrent_hash,
                "display_state": req.processing_status.replace("_", " ").title(),
                "stage": _status_stage(req.processing_status, req.download_progress)[0],
                "stage_label": _status_stage(req.processing_status, req.download_progress)[1],
                "error_reason": req.processing_status.split(":", 1)[1].strip()
                if req.processing_status.startswith("failed:")
                else None,
                "logs": [
                    {
                        "message": log.message,
                        "level": log.level.value,
                        "timestamp": log.created_at.strftime("%b %d %H:%M"),
                    }
                    for log in get_request_logs(
                        session,
                        req.asin,
                        None if user.is_admin() else user.username,
                    )
                ],
            }
        )

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


@router.get("/attention")
async def attention(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(ABRAuth())],
    filter: Annotated[list[str] | None, Query()] = None,
):
    username = None if user.is_admin() else user.username
    active_filters = filter or []
    filter_query = ""
    if active_filters:
        filter_query = "?" + "&".join([f"filter={f}" for f in active_filters])
    results, issue_map = _build_attention_results(session, username, active_filters)
    counts = get_wishlist_counts(session, user)
    return template_response(
        "wishlist_page/wishlist.html",
        request,
        user,
        {
            "results": results,
            "page": "attention",
            "counts": counts,
            "issue_map": issue_map,
            "active_filters": active_filters,
            "filter_query": filter_query,
        },
    )


@router.post("/retry/{asin}")
async def retry_request(
    request: Request,
    asin: str,
    session: Annotated[Session, Depends(get_session)],
    background_task: BackgroundTasks,
    user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.trusted))],
):
    statement = select(AudiobookRequest).where(AudiobookRequest.asin == asin)
    if not user.is_admin():
        statement = statement.where(AudiobookRequest.user_username == user.username)
    req = session.exec(statement).first()
    if not req:
        raise ToastException("Request not found.", "error")

    req.processing_status = "pending"
    req.download_progress = 0.0
    req.download_state = "queued"
    req.torrent_hash = None
    session.add(req)
    session.commit()
    log_request_event(
        session,
        req.asin,
        req.user_username,
        "Retry requested. Re-queueing auto-download.",
        commit=True,
    )
    background_task.add_task(
        background_start_query,
        asin=asin,
        requester=User.model_validate(user),
        auto_download=True,
    )

    return await active_downloads(request, session, user)


@router.post("/bulk/retry")
async def bulk_retry(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    background_task: BackgroundTasks,
    user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.trusted))],
    asins: Annotated[list[str], Form()] = [],
):
    username = None if user.is_admin() else user.username
    for asin in asins:
        statement = select(AudiobookRequest).where(AudiobookRequest.asin == asin)
        if username:
            statement = statement.where(AudiobookRequest.user_username == username)
        req = session.exec(statement).first()
        if not req:
            continue
        req.processing_status = "pending"
        req.download_progress = 0.0
        req.download_state = "queued"
        req.torrent_hash = None
        session.add(req)
        log_request_event(
            session,
            req.asin,
            req.user_username,
            "Retry requested. Re-queueing auto-download.",
            commit=False,
        )
        background_task.add_task(
            background_start_query,
            asin=asin,
            requester=User.model_validate(user),
            auto_download=True,
        )

    session.commit()

    results, issue_map = _build_attention_results(
        session, username, request.query_params.getlist("filter")
    )
    counts = get_wishlist_counts(session, user)
    return template_response(
        "wishlist_page/wishlist.html",
        request,
        user,
        {
            "results": results,
            "page": "attention",
            "counts": counts,
            "issue_map": issue_map,
            "active_filters": request.query_params.getlist("filter"),
            "filter_query": "?"
            + "&".join(
                [f"filter={f}" for f in request.query_params.getlist("filter")]
            )
            if request.query_params.getlist("filter")
            else "",
            "update_tablist": True,
        },
        block_name="book_wishlist",
    )


@router.post("/bulk/auto-download")
async def bulk_auto_download(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    background_task: BackgroundTasks,
    user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.trusted))],
    asins: Annotated[list[str], Form()] = [],
):
    username = None if user.is_admin() else user.username
    for asin in asins:
        statement = select(AudiobookRequest).where(AudiobookRequest.asin == asin)
        if username:
            statement = statement.where(AudiobookRequest.user_username == username)
        req = session.exec(statement).first()
        if not req:
            continue
        log_request_event(
            session,
            req.asin,
            req.user_username,
            "Bulk auto-download requested.",
            commit=False,
        )
        background_task.add_task(
            background_start_query,
            asin=asin,
            requester=User.model_validate(user),
            auto_download=True,
        )

    session.commit()
    page = request.query_params.get("page", "wishlist")
    return _render_wishlist_page(request, session, user, page)


@router.post("/bulk/mark-downloaded")
async def bulk_mark_downloaded(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    background_task: BackgroundTasks,
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
    asins: Annotated[list[str], Form()] = [],
):
    for asin in asins:
        try:
            await api_mark_downloaded(asin, session, background_task, admin_user)
        except HTTPException:
            continue
    page = request.query_params.get("page", "wishlist")
    return _render_wishlist_page(request, session, admin_user, page)


@router.post("/bulk/delete")
async def bulk_delete(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(ABRAuth())],
    asins: Annotated[list[str], Form()] = [],
):
    for asin in asins:
        try:
            await api_delete_request(asin, session, user)
        except HTTPException:
            continue

    page = request.query_params.get("page", "attention")
    if page != "attention":
        return _render_wishlist_page(request, session, user, page)

    username = None if user.is_admin() else user.username
    results, issue_map = _build_attention_results(
        session, username, request.query_params.getlist("filter")
    )
    counts = get_wishlist_counts(session, user)

    return template_response(
        "wishlist_page/wishlist.html",
        request,
        user,
        {
            "results": results,
            "page": "attention",
            "counts": counts,
            "issue_map": issue_map,
            "active_filters": request.query_params.getlist("filter"),
            "filter_query": "?"
            + "&".join(
                [f"filter={f}" for f in request.query_params.getlist("filter")]
            )
            if request.query_params.getlist("filter")
            else "",
            "update_tablist": True,
        },
        block_name="book_wishlist",
    )


@router.get("/review/{asin}")
async def review_metadata(
    request: Request,
    asin: str,
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    book = session.get(Audiobook, asin)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    req = session.exec(
        select(AudiobookRequest).where(AudiobookRequest.asin == asin)
    ).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    return template_response(
        "wishlist_page/review.html",
        request,
        admin_user,
        {
            "book": book,
            "request": req,
            "authors_str": ", ".join(book.authors or []),
            "narrators_str": ", ".join(book.narrators or []),
            "series_str": ", ".join(book.series or []),
        },
    )


@router.post("/review/{asin}")
async def review_metadata_submit(
    request: Request,
    asin: str,
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
    title: Annotated[str, Form()],
    subtitle: Annotated[str | None, Form()] = None,
    authors: Annotated[str | None, Form()] = None,
    narrators: Annotated[str | None, Form()] = None,
    series: Annotated[str | None, Form()] = None,
    action: Annotated[str | None, Form()] = None,
):
    book = session.get(Audiobook, asin)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    req = session.exec(
        select(AudiobookRequest).where(AudiobookRequest.asin == asin)
    ).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    def parse_list(value: str | None) -> list[str]:
        if not value:
            return []
        return [v.strip() for v in value.split(",") if v.strip()]

    book.title = title.strip()
    book.subtitle = subtitle.strip() if subtitle else None
    book.authors = parse_list(authors)
    book.narrators = parse_list(narrators)
    book.series = parse_list(series)
    session.add(book)
    session.commit()
    log_request_event(
        session,
        asin,
        req.user_username,
        "Metadata reviewed and updated.",
        commit=True,
    )

    if action == "import":
        from app.internal.download_clients.qbittorrent import QbittorrentClient
        from app.internal.processing.processor import process_completed_download

        client = QbittorrentClient(session)
        torrents = await client.get_torrents()
        matching_torrent = None
        for t in torrents:
            if f"asin:{asin}" in t.get("tags", ""):
                matching_torrent = t
                break
        if not matching_torrent:
            raise ToastException("No matching torrent found for this request.", "error")

        download_path = matching_torrent.get("content_path")
        if not download_path:
            raise ToastException("Torrent content path is missing.", "error")

        req.processing_status = "queued"
        session.add(req)
        session.commit()
        log_request_event(
            session,
            asin,
            req.user_username,
            "Metadata approved. Starting import.",
            commit=True,
        )

        await process_completed_download(session, req, download_path)
        await client.add_torrent_tags(matching_torrent.get("hash"), ["processed"])
        await client.delete_torrent(matching_torrent.get("hash"), delete_files=False)

        return BaseUrlRedirectResponse("/wishlist/downloading")

    return template_response(
        "wishlist_page/review.html",
        request,
        admin_user,
        {
            "book": book,
            "request": req,
            "authors_str": ", ".join(book.authors or []),
            "narrators_str": ", ".join(book.narrators or []),
            "series_str": ", ".join(book.series or []),
            "success": "Metadata saved. Review is still required before import.",
        },
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
        raise ToastException(
            "Could not find a matching torrent in qBittorrent for this ASIN.", "error"
        )

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
