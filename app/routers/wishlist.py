import aiohttp
from app.util.toast import ToastException
from sqlalchemy.orm import InstrumentedAttribute, selectinload
from app.internal.models import AudiobookWishlistResult
from app.internal.models import Audiobook
import uuid
from typing import Annotated, Literal, cast

from aiohttp import ClientSession
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Form,
    HTTPException,
    Request,
    Response,
    Security,
)
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import Session, asc, col, not_, select

from app.internal.auth.authentication import ABRAuth, DetailedUser
from app.internal.models import (
    AudiobookRequest,
    EventEnum,
    GroupEnum,
    ManualBookRequest,
    User,
)
from app.internal.notifications import (
    send_all_manual_notifications,
    send_all_notifications,
)
from app.internal.prowlarr.prowlarr import (
    ProwlarrMisconfigured,
    prowlarr_config,
    start_download,
)
from app.internal.query import query_sources
from app.util.connection import get_connection
from app.util.db import get_session, open_session
from app.util.redirect import BaseUrlRedirectResponse
from app.util.templates import template_response

router = APIRouter(prefix="/wishlist")


class WishlistCounts(BaseModel):
    requests: int
    downloaded: int
    manual: int


def get_wishlist_counts(session: Session, user: User | None = None) -> WishlistCounts:
    """
    If a non-admin user is given, only count requests for that user.
    Admins can see and get counts for all requests.
    """
    username = None if user is None or user.is_admin() else user.username

    rows = session.exec(
        select(Audiobook.downloaded, func.count("*"))
        .where(not username or AudiobookRequest.user_username == username)
        .select_from(Audiobook)
        .join(AudiobookRequest)
        .group_by(col(Audiobook.downloaded))
    ).all()
    requests = 0
    downloaded = 0
    for downloaded_status, count in rows:
        if downloaded_status:
            downloaded = count
        else:
            requests = count

    manual = session.exec(
        select(func.count())
        .select_from(ManualBookRequest)
        .where(
            not username or ManualBookRequest.user_username == username,
            col(ManualBookRequest.user_username).is_not(None),
        )
    ).one()

    return WishlistCounts(
        requests=requests,
        downloaded=downloaded,
        manual=manual,
    )


def get_wishlist_results(
    session: Session,
    username: str | None = None,
    response_type: Literal["all", "downloaded", "not_downloaded"] = "all",
) -> list[AudiobookWishlistResult]:
    """
    Gets the books that have been requested. If a username is given only the books requested by that
    user are returned. If no username is given, all book requests are returned.
    """
    match response_type:
        case "downloaded":
            clause = Audiobook.downloaded
        case "not_downloaded":
            clause = not_(Audiobook.downloaded)
        case _:
            clause = True

    results = session.exec(
        select(Audiobook)
        .where(
            clause,
            col(Audiobook.asin).in_(
                select(AudiobookRequest.asin).where(
                    not username or AudiobookRequest.user_username == username
                )
            ),
        )
        .options(
            selectinload(
                cast(
                    InstrumentedAttribute[list[AudiobookRequest]],
                    cast(object, Audiobook.requests),
                )
            )
        )
    ).all()

    return [
        AudiobookWishlistResult(
            book=book,
            requests=book.requests,
        )
        for book in results
    ]


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


@router.patch("/downloaded/{asin}")
async def update_downloaded(
    request: Request,
    asin: str,
    session: Annotated[Session, Depends(get_session)],
    background_task: BackgroundTasks,
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
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

    username = None if admin_user.is_admin() else admin_user.username
    results = get_wishlist_results(session, username, "not_downloaded")
    counts = get_wishlist_counts(session, admin_user)

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


def _get_all_manual_requests(session: Session, user: User):
    return session.exec(
        select(ManualBookRequest)
        .where(
            user.is_admin() or ManualBookRequest.user_username == user.username,
            col(ManualBookRequest.user_username).is_not(None),
        )
        .order_by(asc(ManualBookRequest.downloaded))
    ).all()


@router.get("/manual")
async def manual(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(ABRAuth())],
):
    books = _get_all_manual_requests(session, user)
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

    books = _get_all_manual_requests(session, admin_user)
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


@router.delete("/manual/{id}")
async def delete_manual(
    request: Request,
    id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    book = session.get(ManualBookRequest, id)
    if book:
        session.delete(book)
        session.commit()

    books = _get_all_manual_requests(session, admin_user)
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


@router.post("/refresh/{asin}")
async def refresh_source(
    asin: str,
    background_task: BackgroundTasks,
    user: Annotated[DetailedUser, Security(ABRAuth())],
    force_refresh: bool = False,
):
    # causes the sources to be placed into cache once they're done
    with open_session() as session:
        async with ClientSession(timeout=aiohttp.ClientTimeout(30)) as client_session:
            background_task.add_task(
                query_sources,
                asin=asin,
                session=session,
                client_session=client_session,
                force_refresh=force_refresh,
                requester=User.model_validate(user),
            )
    return Response(status_code=202)


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
        prowlarr_config.raise_if_invalid(session)
    except ProwlarrMisconfigured:
        return BaseUrlRedirectResponse(
            "/settings/prowlarr?prowlarr_misconfigured=1", status_code=302
        )

    result = await query_sources(
        asin,
        session=session,
        client_session=client_session,
        requester=admin_user,
        only_return_if_cached=not only_body,  # on initial load we want to respond quickly
    )

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
    asin: str,
    guid: Annotated[str, Form()],
    indexer_id: Annotated[int, Form()],
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    try:
        resp = await start_download(
            session=session,
            client_session=client_session,
            guid=guid,
            indexer_id=indexer_id,
            requester=admin_user,
            book_asin=asin,
        )
    except ProwlarrMisconfigured as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not resp.ok:
        raise HTTPException(status_code=500, detail="Failed to start download")

    book = session.exec(select(Audiobook).where(Audiobook.asin == asin)).first()
    if book:
        book.downloaded = True
        session.add(book)
        session.commit()

    return Response(status_code=204)


@router.post("/auto-download/{asin}")
async def start_auto_download(
    request: Request,
    asin: str,
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.trusted))],
):
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
