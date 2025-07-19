from typing import Annotated, Optional

from sqlalchemy.exc import IntegrityError
from aiohttp import ClientSession
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Form,
    HTTPException,
    Query,
    Request,
)
from sqlmodel import Session, col, select

from app.internal import book_search
from app.internal.book_search import (
    audible_region_type,
    audible_regions,
    get_book_by_asin,
    get_region_from_settings,
    list_audible_books,
)
from app.internal.models import (
    BookRequest,
    BookSearchResult,
    EventEnum,
    GroupEnum,
    ManualBookRequest,
)
from app.internal.notifications import (
    send_all_manual_notifications,
    send_all_notifications,
)
from app.internal.prowlarr.prowlarr import prowlarr_config
from app.internal.query import query_sources
from app.internal.ranking.quality import quality_config
from app.routers.wishlist import get_wishlist_books
from app.internal.auth.authentication import DetailedUser, get_authenticated_user
from app.util.connection import get_connection
from app.util.db import get_session, open_session
from app.util.templates import template_response

router = APIRouter(prefix="/search")


def get_already_requested(session: Session, results: list[BookRequest], username: str):
    books: list[BookSearchResult] = []
    if len(results) > 0:
        # check what books are already requested by the user
        asins = {book.asin for book in results}
        requested_books = set(
            session.exec(
                select(BookRequest.asin).where(
                    col(BookRequest.asin).in_(asins),
                    BookRequest.user_username == username,
                )
            ).all()
        )

        for book in results:
            book_search = BookSearchResult.model_validate(book)
            if book.asin in requested_books:
                book_search.already_requested = True
            books.append(book_search)
    return books


@router.get("")
async def read_search(
    request: Request,
    user: Annotated[DetailedUser, Depends(get_authenticated_user())],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    session: Annotated[Session, Depends(get_session)],
    query: Annotated[Optional[str], Query(alias="q")] = None,
    num_results: int = 20,
    page: int = 0,
    region: audible_region_type = get_region_from_settings(),
):
    if audible_regions.get(region) is None:
        raise HTTPException(status_code=400, detail="Invalid region")
    if query:
        results = await list_audible_books(
            session=session,
            client_session=client_session,
            query=query,
            num_results=num_results,
            page=page,
            audible_region=region,
        )
    else:
        results = []

    books: list[BookSearchResult] = []
    if len(results) > 0:
        books = get_already_requested(session, results, user.username)

    prowlarr_configured = prowlarr_config.is_valid(session)

    return template_response(
        "search.html",
        request,
        user,
        {
            "search_term": query or "",
            "search_results": books,
            "regions": audible_regions,
            "selected_region": region,
            "page": page,
            "auto_start_download": quality_config.get_auto_download(session)
            and user.is_above(GroupEnum.trusted),
            "prowlarr_configured": prowlarr_configured,
        },
    )


@router.get("/suggestions")
async def search_suggestions(
    request: Request,
    user: Annotated[DetailedUser, Depends(get_authenticated_user())],
    query: Annotated[str, Query(alias="q")],
    region: audible_region_type = get_region_from_settings(),
):
    async with ClientSession() as client_session:
        suggestions = await book_search.get_search_suggestions(
            client_session, query, region
        )
        return template_response(
            "search.html",
            request,
            user,
            {"suggestions": suggestions},
            block_name="search_suggestions",
        )


async def background_start_query(
    asin: str, requester_username: str, auto_download: bool
):
    with open_session() as session:
        async with ClientSession() as client_session:
            await query_sources(
                asin=asin,
                session=session,
                client_session=client_session,
                start_auto_download=auto_download,
                requester_username=requester_username,
            )


@router.post("/request/{asin}")
async def add_request(
    request: Request,
    asin: str,
    user: Annotated[DetailedUser, Depends(get_authenticated_user())],
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    background_task: BackgroundTasks,
    query: Annotated[Optional[str], Form()],
    page: Annotated[int, Form()],
    region: Annotated[audible_region_type, Form()],
    num_results: Annotated[int, Form()] = 20,
):
    book = await get_book_by_asin(client_session, asin, region)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    book.user_username = user.username
    try:
        session.add(book)
        session.commit()
    except IntegrityError:
        pass  # ignore if already exists

    background_task.add_task(
        send_all_notifications,
        event_type=EventEnum.on_new_request,
        requester_username=user.username,
        book_asin=asin,
    )

    if quality_config.get_auto_download(session) and user.is_above(GroupEnum.trusted):
        # start querying and downloading if auto download is enabled
        background_task.add_task(
            background_start_query,
            asin=asin,
            requester_username=user.username,
            auto_download=True,
        )

    if audible_regions.get(region) is None:
        raise HTTPException(status_code=400, detail="Invalid region")
    if query:
        results = await list_audible_books(
            session=session,
            client_session=client_session,
            query=query,
            num_results=num_results,
            page=page,
            audible_region=region,
        )
    else:
        results = []

    books: list[BookSearchResult] = []
    if len(results) > 0:
        books = get_already_requested(session, results, user.username)

    prowlarr_configured = prowlarr_config.is_valid(session)

    return template_response(
        "search.html",
        request,
        user,
        {
            "search_term": query or "",
            "search_results": books,
            "regions": audible_regions,
            "selected_region": region,
            "page": page,
            "auto_start_download": quality_config.get_auto_download(session)
            and user.is_above(GroupEnum.trusted),
            "prowlarr_configured": prowlarr_configured,
        },
        block_name="book_results",
    )


@router.delete("/request/{asin}")
async def delete_request(
    request: Request,
    asin: str,
    admin_user: Annotated[
        DetailedUser, Depends(get_authenticated_user(GroupEnum.admin))
    ],
    session: Annotated[Session, Depends(get_session)],
    downloaded: Optional[bool] = None,
):
    books = session.exec(select(BookRequest).where(BookRequest.asin == asin)).all()
    if books:
        [session.delete(b) for b in books]
        session.commit()

    books = get_wishlist_books(
        session, None, "downloaded" if downloaded else "not_downloaded"
    )

    return template_response(
        "wishlist_page/wishlist.html",
        request,
        admin_user,
        {"books": books, "page": "downloaded" if downloaded else "wishlist"},
        block_name="book_wishlist",
    )


@router.get("/manual")
async def read_manual(
    request: Request,
    user: Annotated[DetailedUser, Depends(get_authenticated_user())],
    session: Annotated[Session, Depends(get_session)],
):
    auto_download = quality_config.get_auto_download(session)
    return template_response(
        "manual.html", request, user, {"auto_download": auto_download}
    )


@router.post("/manual")
async def add_manual(
    request: Request,
    user: Annotated[DetailedUser, Depends(get_authenticated_user())],
    session: Annotated[Session, Depends(get_session)],
    background_task: BackgroundTasks,
    title: Annotated[str, Form()],
    author: Annotated[str, Form()],
    narrator: Annotated[Optional[str], Form()] = None,
    subtitle: Annotated[Optional[str], Form()] = None,
    publish_date: Annotated[Optional[str], Form()] = None,
    info: Annotated[Optional[str], Form()] = None,
):
    book_request = ManualBookRequest(
        user_username=user.username,
        title=title,
        authors=author.split(","),
        narrators=narrator.split(",") if narrator else [],
        subtitle=subtitle,
        publish_date=publish_date,
        additional_info=info,
    )
    session.add(book_request)
    session.flush()
    session.expunge_all()  # so that we can pass down the object without the session
    session.commit()

    background_task.add_task(
        send_all_manual_notifications,
        event_type=EventEnum.on_new_request,
        book_request=book_request,
    )

    auto_download = quality_config.get_auto_download(session)

    return template_response(
        "manual.html",
        request,
        user,
        {"success": "Successfully added request", "auto_download": auto_download},
        block_name="form",
    )
