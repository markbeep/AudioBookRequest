import uuid
from typing import Annotated, Literal

from aiohttp import ClientSession
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Security,
    Response,
)
from pydantic import BaseModel
from sqlmodel import Session, asc, col, select, delete

from app.internal.audiobookshelf.client import background_abs_trigger_scan
from app.internal.audiobookshelf.config import abs_config
from app.internal.auth.authentication import APIKeyAuth, DetailedUser
from app.internal.book_search import (
    get_book_by_asin,
    audible_region_type,
    get_region_from_settings,
    audible_regions,
)
from app.internal.library.service import library_contains_asin
from app.internal.models import (
    Audiobook,
    AudiobookRequest,
    AudiobookWishlistResult,
    EventEnum,
    GroupEnum,
    ManualBookRequest,
    User,
)
from app.internal.notifications import (
    send_all_manual_notifications,
    send_all_notifications,
)
from app.internal.prowlarr.prowlarr import start_download
from app.internal.prowlarr.util import ProwlarrMisconfigured, prowlarr_config
from app.internal.query import query_sources, QueryResult, background_start_query
from app.internal.ranking.quality import quality_config
from app.internal.db_queries import get_wishlist_results
from app.internal.request_logs import log_request_event
from app.util.connection import get_connection
from app.util.db import get_session
from app.util.log import logger
from app.util.toast import ToastException

router = APIRouter(prefix="/requests", tags=["Requests"])


class DownloadSourceBody(BaseModel):
    guid: str
    indexer_id: int


@router.post("/{asin}", status_code=201)
async def create_request(
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    user: Annotated[DetailedUser, Security(APIKeyAuth())],
    background_task: BackgroundTasks,
    asin: str,
    region: audible_region_type | None = None,
):
    if region is None:
        region = get_region_from_settings()
    if audible_regions.get(region) is None:
        raise HTTPException(status_code=400, detail="Invalid region")

    book = await get_book_by_asin(client_session, asin, region)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if library_contains_asin(session, asin):
        raise HTTPException(
            status_code=400, detail="Book already exists in library folder"
        )

    if book.downloaded:
        raise HTTPException(status_code=400, detail="Book already in library")

    if not session.exec(
        select(AudiobookRequest).where(
            AudiobookRequest.asin == asin,
            AudiobookRequest.user_username == user.username,
        )
    ).first():
        book_request = AudiobookRequest(asin=asin, user_username=user.username)
        session.add(book_request)
        session.commit()
        log_request_event(
            session,
            asin,
            user.username,
            "Request created.",
            commit=True,
        )
        logger.info(
            "Added new audiobook request",
            username=user.username,
            asin=asin,
        )
    else:
        raise HTTPException(status_code=409, detail="Book already requested")

    background_task.add_task(
        send_all_notifications,
        event_type=EventEnum.on_new_request,
        requester=User.model_validate(user),
        book_asin=asin,
    )

    if quality_config.get_auto_download(session) and user.is_above(GroupEnum.trusted):
        # start querying and downloading if auto download is enabled
        background_task.add_task(
            background_start_query,
            asin=asin,
            requester=User.model_validate(user),
            auto_download=True,
        )

    return Response(status_code=201)


@router.get("", response_model=list[AudiobookWishlistResult])
async def list_requests(
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(APIKeyAuth())],
    filter: Literal["all", "downloaded", "not_downloaded"] = "all",
):
    username = None if user.is_admin() else user.username
    results = get_wishlist_results(session, username, filter)
    return results


@router.delete("/{asin}")
async def delete_request(
    asin: str,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(APIKeyAuth())],
):
    from app.internal.download_clients.qbittorrent import QbittorrentClient
    from app.internal.download_clients.config import download_client_config

    # Try to delete from qBittorrent if enabled
    if download_client_config.get_qbit_enabled(session):
        try:
            client = QbittorrentClient(session)
            torrents = await client.get_torrents()
            for t in torrents:
                if f"asin:{asin}" in t.get("tags", ""):
                    await client.delete_torrents([t["hash"]], delete_files=True)
                    logger.info(
                        "Deleted torrent from qBittorrent for deleted request",
                        asin=asin,
                        hash=t["hash"],
                    )
        except Exception as e:
            logger.warning(
                "Failed to delete torrent from qBittorrent during request deletion",
                asin=asin,
                error=str(e),
            )

    if user.is_admin():
        session.execute(
            delete(AudiobookRequest).where(col(AudiobookRequest.asin) == asin)
        )
    else:
        session.execute(
            delete(AudiobookRequest).where(
                (col(AudiobookRequest.asin) == asin)
                & (col(AudiobookRequest.user_username) == user.username)
            )
        )
    session.commit()
    return Response(status_code=204)


@router.patch("/{asin}/downloaded")
async def mark_downloaded(
    asin: str,
    session: Annotated[Session, Depends(get_session)],
    background_task: BackgroundTasks,
    _: Annotated[DetailedUser, Security(APIKeyAuth(GroupEnum.admin))],
):
    book = session.exec(select(Audiobook).where(Audiobook.asin == asin)).first()
    if book:
        book.downloaded = True
        session.add(book)
        session.commit()

        background_task.add_task(
            send_all_notifications,
            event_type=EventEnum.on_successful_download,
            requester=None,
            book_asin=asin,
        )
        return Response(status_code=204)
    raise HTTPException(status_code=404, detail="Book not found")


@router.get("/manual", response_model=list[ManualBookRequest])
async def list_manual_requests(
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(APIKeyAuth())],
):
    return session.exec(
        select(ManualBookRequest)
        .where(
            user.is_admin() or ManualBookRequest.user_username == user.username,
            col(ManualBookRequest.user_username).is_not(None),
        )
        .order_by(asc(ManualBookRequest.downloaded))
    ).all()


class ManualRequest(BaseModel):
    title: str
    author: str
    narrator: str | None = None
    subtitle: str | None = None
    publish_date: str | None = None
    info: str | None = None


@router.post("/manual", status_code=201)
async def create_manual_request(
    body: ManualRequest,
    session: Annotated[Session, Depends(get_session)],
    background_task: BackgroundTasks,
    user: Annotated[DetailedUser, Security(APIKeyAuth())],
):
    book_request = ManualBookRequest(
        user_username=user.username,
        title=body.title,
        authors=body.author.split(","),
        narrators=body.narrator.split(",") if body.narrator else [],
        subtitle=body.subtitle,
        publish_date=body.publish_date,
        additional_info=body.info,
    )
    session.add(book_request)
    session.commit()

    background_task.add_task(
        send_all_manual_notifications,
        event_type=EventEnum.on_new_request,
        book_request=ManualBookRequest.model_validate(book_request),
    )
    return Response(status_code=201)


@router.put("/manual/{id}", status_code=204)
async def update_manual_request(
    id: uuid.UUID,
    body: ManualRequest,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(APIKeyAuth())],
):
    book_request = session.get(ManualBookRequest, id)
    if not book_request:
        raise HTTPException(status_code=404, detail="Book request not found")

    if not user.is_admin() and book_request.user_username != user.username:
        raise HTTPException(status_code=403, detail="Not authorized")

    book_request.title = body.title
    book_request.subtitle = body.subtitle
    book_request.authors = body.author.split(",")
    book_request.narrators = body.narrator.split(",") if body.narrator else []
    book_request.publish_date = body.publish_date
    book_request.additional_info = body.info

    session.add(book_request)
    session.commit()
    return Response(status_code=204)


@router.patch("/manual/{id}/downloaded")
async def mark_manual_downloaded(
    id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    background_task: BackgroundTasks,
    _: Annotated[DetailedUser, Security(APIKeyAuth(GroupEnum.admin))],
):
    book_request = session.get(ManualBookRequest, id)
    if book_request:
        book_request.downloaded = True
        session.add(book_request)
        session.commit()

        background_task.add_task(
            send_all_manual_notifications,
            event_type=EventEnum.on_successful_download,
            book_request=ManualBookRequest.model_validate(book_request),
        )
        return Response(status_code=204)
    raise HTTPException(status_code=404, detail="Request not found")


@router.delete("/manual/{id}")
async def delete_manual_request(
    id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    _: Annotated[DetailedUser, Security(APIKeyAuth(GroupEnum.admin))],
):
    book = session.get(ManualBookRequest, id)
    if book:
        session.delete(book)
        session.commit()
        return Response(status_code=204)
    raise HTTPException(status_code=404, detail="Request not found")


@router.post(
    "/{asin}/refresh",
    description="Refresh the sources from prowlarr for a book",
)
async def refresh_source(
    asin: str,
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    user: Annotated[DetailedUser, Security(APIKeyAuth())],
    force_refresh: bool = False,
):
    # causes the sources to be placed into cache once they're done
    await query_sources(
        asin=asin,
        session=session,
        client_session=client_session,
        force_refresh=force_refresh,
        requester=User.model_validate(user),
    )
    return Response(status_code=202)


@router.get("/{asin}/sources", response_model=QueryResult)
async def list_sources(
    asin: str,
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    admin_user: Annotated[DetailedUser, Security(APIKeyAuth(GroupEnum.admin))],
    only_cached: bool = False,
):
    try:
        prowlarr_config.raise_if_invalid(session)
    except ProwlarrMisconfigured:
        raise HTTPException(status_code=400, detail="Prowlarr misconfigured")

    result = await query_sources(
        asin,
        session=session,
        client_session=client_session,
        requester=admin_user,
        only_return_if_cached=only_cached,
    )
    return result


@router.post("/{asin}/download")
async def download_book(
    asin: str,
    background_task: BackgroundTasks,
    body: DownloadSourceBody,
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    admin_user: Annotated[DetailedUser, Security(APIKeyAuth(GroupEnum.admin))],
):
    book_request = session.exec(
        select(AudiobookRequest)
        .join(Audiobook)
        .where(
            AudiobookRequest.asin == asin,
            Audiobook.downloaded.is_(False),  # Correctly check Audiobook.downloaded
        )
    ).first()

    if not book_request:
        raise HTTPException(
            status_code=404, detail="Active request for this audiobook not found."
        )

    try:
        from app.internal.prowlarr.util import prowlarr_source_cache

        book = session.get(Audiobook, asin)
        sources = prowlarr_source_cache.get(
            prowlarr_config.get_source_ttl(session), book.title if book else ""
        )
        source = None
        if sources:
            source = next(
                (
                    s
                    for s in sources
                    if s.guid == body.guid and s.indexer_id == body.indexer_id
                ),
                None,
            )

        if not source:
            raise HTTPException(
                status_code=404, detail="Source not found in cache for this book."
            )

        success = await start_download(  # start_download now returns bool
            session=session,
            client_session=client_session,
            guid=body.guid,
            indexer_id=body.indexer_id,
            requester=admin_user,
            audiobook_request=book_request,  # Pass the AudiobookRequest object
            prowlarr_source=source,  # prowlarr_source is now required
        )
    except ProwlarrMisconfigured as e:
        logger.error("Prowlarr misconfigured for download", error=str(e))
        background_task.add_task(
            send_all_notifications,
            event_type=EventEnum.on_failed_download,
            requester=admin_user,
            book_asin=asin,
            other_replacements={
                "errorStatus": "500",
                "errorReason": str(e),
            },
        )
        raise HTTPException(status_code=500, detail=str(e))

    # Check success (start_download now returns bool directly)
    if not success:
        logger.error("Failed to start download via qBittorrent", asin=asin)
        background_task.add_task(
            send_all_notifications,
            event_type=EventEnum.on_failed_download,
            requester=admin_user,
            book_asin=asin,
            other_replacements={
                "errorStatus": "500",
                "errorReason": "Failed to start download",
            },
        )
        raise HTTPException(status_code=500, detail="Failed to start download")

    # Notifications are handled here after successful start of download
    additional_replacements: dict[str, str] = {"bookASIN": asin}
    background_task.add_task(
        send_all_notifications,
        event_type=EventEnum.on_successful_download,
        requester=admin_user,
        book_asin=asin,
        other_replacements=additional_replacements,
    )

    if abs_config.is_valid(session):
        background_task.add_task(background_abs_trigger_scan)

    return Response(status_code=204)


@router.post("/{asin}/auto-download")
async def start_auto_download_endpoint(
    asin: str,
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    user: Annotated[DetailedUser, Security(APIKeyAuth(GroupEnum.trusted))],
):
    log_request_event(
        session,
        asin,
        user.username,
        "Auto-download queued.",
        commit=True,
    )
    try:
        await query_sources(
            asin=asin,
            start_auto_download=True,
            session=session,
            client_session=client_session,
            requester=user,
        )
    except HTTPException as e:
        raise ToastException(e.detail) from None

    return Response(status_code=204)
