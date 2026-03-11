import uuid
from typing import Annotated, Literal

from aiohttp import ClientSession
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Response,
    Security,
)
from pydantic import BaseModel
from sqlmodel import Session, asc, col, delete, select

from app.internal.audible.single import get_single_book
from app.internal.audible.types import (
    audible_region_type,
    audible_regions,
    get_region_from_settings,
)
from app.internal.audiobookshelf.client import background_abs_trigger_scan
from app.internal.audiobookshelf.config import abs_config
from app.internal.auth.authentication import AnyAuth, DetailedUser
from app.internal.db_queries import get_wishlist_results
from app.internal.models import (
    Audiobook,
    AudiobookRequest,
    AudiobookWishlistResult,
    AudiobookWithRequests,
    EventEnum,
    GroupEnum,
    ManualBookRequest,
)
from app.internal.notifications import (
    send_all_manual_notifications,
    send_all_notifications,
)
from app.internal.prowlarr.prowlarr import start_download
from app.internal.prowlarr.util import ProwlarrMisconfigured, prowlarr_config
from app.internal.query import QueryResult, background_start_query, query_sources
from app.internal.ranking.quality import quality_config
from app.util.censor import censor
from app.util.connection import get_connection
from app.util.db import get_session
from app.util.log import logger
from app.util.toast import ToastException

router = APIRouter(prefix="/requests", tags=["Requests"])


class DownloadSourceBody(BaseModel):
    guid: str
    indexer_id: int


@router.post("/{asin_or_uuid}", response_model=Audiobook)
async def create_request(
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    user: Annotated[DetailedUser, Security(AnyAuth())],
    background_task: BackgroundTasks,
    asin_or_uuid: str,
    region: audible_region_type | None = None,
) -> AudiobookWithRequests:
    if region is None:
        region = get_region_from_settings()
    if audible_regions.get(region) is None:
        raise HTTPException(status_code=400, detail="Invalid region")

    book = session.get(Audiobook, asin_or_uuid)
    if not book:
        try:
            book = await get_single_book(client_session, asin=asin_or_uuid)
            if book:
                session.add(book)
                session.commit()
        except Exception as e:
            logger.error(
                "Failed to fetch book details from Audible",
                asin=asin_or_uuid,
                error=str(e),
            )
        if not book:
            raise HTTPException(status_code=404, detail="Book not found")

    if not session.exec(
        select(AudiobookRequest).where(
            AudiobookRequest.asin == asin_or_uuid,
            AudiobookRequest.user_username == user.username,
        )
    ).first():
        book_request = AudiobookRequest(asin=asin_or_uuid, user_username=user.username)
        session.add(book_request)
        session.commit()
        logger.info(
            "Added new audiobook request",
            username=censor(user.username),
            asin=asin_or_uuid,
        )
    else:
        raise HTTPException(status_code=409, detail="Book already requested")

    background_task.add_task(
        send_all_notifications,
        event_type=EventEnum.on_new_request,
        book_asin=asin_or_uuid,
    )

    if quality_config.get_auto_download(session) and user.is_above(GroupEnum.trusted):
        # start querying and downloading if auto download is enabled
        background_task.add_task(
            background_start_query,
            asin_or_uuid=asin_or_uuid,
            auto_download=True,
        )

    requests = session.exec(
        select(AudiobookRequest).where(AudiobookRequest.asin == asin_or_uuid)
    ).all()

    return AudiobookWithRequests(
        book=book,
        requests=list(requests),
        username=user.username,
    )


@router.get("", response_model=list[AudiobookWishlistResult])
async def list_requests(
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(AnyAuth())],
    filter: Literal["all", "downloaded", "not_downloaded"] = "all",
):
    username = None if user.is_admin() else user.username
    results = get_wishlist_results(session, username, filter)
    return results


@router.delete("/{asin_or_uuid}")
async def delete_request(
    asin_or_uuid: str,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(AnyAuth())],
):
    if user.is_admin():
        session.execute(
            delete(AudiobookRequest).where(col(AudiobookRequest.asin) == asin_or_uuid)
        )
    else:
        session.execute(
            delete(AudiobookRequest).where(
                (col(AudiobookRequest.asin) == asin_or_uuid)
                & (col(AudiobookRequest.user_username) == user.username)
            )
        )
    session.commit()
    return Response(status_code=204)


@router.patch("/{asin_or_uuid}/downloaded")
async def mark_downloaded(
    asin_or_uuid: str,
    session: Annotated[Session, Depends(get_session)],
    background_task: BackgroundTasks,
    _: Annotated[DetailedUser, Security(AnyAuth(GroupEnum.admin))],
):
    book = session.exec(select(Audiobook).where(Audiobook.asin == asin_or_uuid)).first()
    if book:
        book.downloaded = True
        session.add(book)
        session.commit()

        background_task.add_task(
            send_all_notifications,
            event_type=EventEnum.on_successful_download,
            book_asin=asin_or_uuid,
        )
        return Response(status_code=204)
    raise HTTPException(status_code=404, detail="Book not found")


@router.get("/manual", response_model=list[ManualBookRequest])
async def list_manual_requests(
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(AnyAuth())],
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
    user: Annotated[DetailedUser, Security(AnyAuth())],
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
    user: Annotated[DetailedUser, Security(AnyAuth())],
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
    _: Annotated[DetailedUser, Security(AnyAuth(GroupEnum.admin))],
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
    _: Annotated[DetailedUser, Security(AnyAuth(GroupEnum.admin))],
):
    book = session.get(ManualBookRequest, id)
    if book:
        session.delete(book)
        session.commit()
        return Response(status_code=204)
    raise HTTPException(status_code=404, detail="Request not found")


@router.post(
    "/{asin_or_uuid}/refresh",
    description="Refresh the sources from prowlarr for a book",
)
async def refresh_source(
    asin_or_uuid: str,
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    user: Annotated[DetailedUser, Security(AnyAuth())],
    force_refresh: bool = False,
):
    _ = user
    # causes the sources to be placed into cache once they're done
    await query_sources(
        asin_or_uuid=asin_or_uuid,
        session=session,
        client_session=client_session,
        force_refresh=force_refresh,
    )
    return Response(status_code=202)


@router.get("/{asin_or_uuid}/sources", response_model=QueryResult)
async def list_sources(
    asin_or_uuid: str,
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    admin_user: Annotated[DetailedUser, Security(AnyAuth(GroupEnum.admin))],
    only_cached: bool = False,
):
    _ = admin_user
    try:
        prowlarr_config.raise_if_invalid(session)
    except ProwlarrMisconfigured:
        raise HTTPException(status_code=400, detail="Prowlarr misconfigured")

    result = await query_sources(
        asin_or_uuid,
        session=session,
        client_session=client_session,
        only_return_if_cached=only_cached,
    )
    return result


@router.post("/{asin_or_uuid}/download")
async def download_book(
    asin_or_uuid: str,
    background_task: BackgroundTasks,
    body: DownloadSourceBody,
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    admin_user: Annotated[DetailedUser, Security(AnyAuth(GroupEnum.admin))],
):
    _ = admin_user
    try:
        resp = await start_download(
            session=session,
            client_session=client_session,
            guid=body.guid,
            indexer_id=body.indexer_id,
            asin_or_uuid=asin_or_uuid,
        )
    except ProwlarrMisconfigured as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not resp.ok:
        raise HTTPException(status_code=500, detail="Failed to start download")

    if abs_config.is_valid(session):
        background_task.add_task(background_abs_trigger_scan)

    return Response(status_code=204)


@router.post("/{asin_or_uuid}/auto-download")
async def start_auto_download_endpoint(
    asin_or_uuid: str,
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    trusted_user: Annotated[DetailedUser, Security(AnyAuth(GroupEnum.trusted))],
):
    _ = trusted_user
    try:
        await query_sources(
            asin_or_uuid=asin_or_uuid,
            start_auto_download=True,
            session=session,
            client_session=client_session,
        )
    except HTTPException as e:
        raise ToastException(e.detail) from None

    return Response(status_code=204)
