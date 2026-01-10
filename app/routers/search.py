import aiohttp
from app.internal.models import AudiobookSearchResult
import uuid
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
from sqlmodel import Session, col, delete, select

from app.internal import book_search
from app.internal.auth.authentication import ABRAuth, DetailedUser
from app.internal.book_search import (
    audible_region_type,
    audible_regions,
    clear_old_book_caches,
    get_book_by_asin,
    get_region_from_settings,
    list_audible_books,
)
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
from app.internal.prowlarr.prowlarr import prowlarr_config
from app.internal.query import query_sources
from app.internal.ranking.quality import quality_config
from app.routers.wishlist import get_wishlist_results, get_wishlist_counts
from app.util.connection import get_connection
from app.util.db import get_session, open_session
from app.util.log import logger
from app.util.templates import template_response

router = APIRouter(prefix="/search")


@router.get("")
async def read_search(
    request: Request,
    client_session: Annotated[ClientSession, Depends(get_connection)],
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(ABRAuth())],
    query: Annotated[str | None, Query(alias="q")] = None,
    num_results: int = 20,
    page: int = 0,
    region: audible_region_type | None = None,
):
    try:
        if region is None:
            region = get_region_from_settings()
        if audible_regions.get(region) is None:
            raise HTTPException(status_code=400, detail="Invalid region")
        if query:
            clear_old_book_caches(session)
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

        results = [
            AudiobookSearchResult(
                book=book,
                requests=book.requests,
                username=user.username,
            )
            for book in results
        ]

        prowlarr_configured = prowlarr_config.is_valid(session)

        return template_response(
            "search.html",
            request,
            user,
            {
                "search_term": query or "",
                "search_results": results,
                "regions": audible_regions,
                "selected_region": region,
                "page": page,
                "auto_start_download": quality_config.get_auto_download(session)
                and user.is_above(GroupEnum.trusted),
                "prowlarr_configured": prowlarr_configured,
            },
        )
    except Exception as e:
        session.rollback()
        logger.exception("Error during search", error=e)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/suggestions")
async def search_suggestions(
    request: Request,
    query: Annotated[str, Query(alias="q")],
    user: Annotated[DetailedUser, Security(ABRAuth())],
    region: audible_region_type | None = None,
):
    if region is None:
        region = get_region_from_settings()
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


async def background_start_query(asin: str, requester: User, auto_download: bool):
    with open_session() as session:
        async with ClientSession(timeout=aiohttp.ClientTimeout(60)) as client_session:
            _ = await query_sources(
                asin=asin,
                session=session,
                client_session=client_session,
                start_auto_download=auto_download,
                requester=requester,
            )


@router.post("/request/{asin}")
async def add_request(
    request: Request,
    asin: str,
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    background_task: BackgroundTasks,
    query: Annotated[str | None, Form()],
    page: Annotated[int, Form()],
    region: Annotated[audible_region_type, Form()],
    user: Annotated[DetailedUser, Security(ABRAuth())],
    num_results: Annotated[int, Form()] = 20,
):
    book = await get_book_by_asin(client_session, asin, region)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if not session.exec(
        select(AudiobookRequest).where(
            AudiobookRequest.asin == asin,
            AudiobookRequest.user_username == user.username,
        )
    ).first():
        book_request = AudiobookRequest(asin=asin, user_username=user.username)
        session.add(book_request)
        session.commit()
        logger.info(
            "Added new audiobook request",
            username=user.username,
            asin=asin,
        )
    else:
        logger.warning(
            "User has already requested this book",
            username=user.username,
            asin=asin,
        )

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

    results = [
        AudiobookSearchResult(
            book=book,
            requests=book.requests,
            username=user.username,
        )
        for book in results
    ]

    prowlarr_configured = prowlarr_config.is_valid(session)

    return template_response(
        "search.html",
        request,
        user,
        {
            "search_term": query or "",
            "search_results": results,
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
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(ABRAuth())],
    downloaded: bool | None = None,
):
    if user.is_admin():
        session.execute(
            delete(AudiobookRequest).where(col(AudiobookRequest.asin) == asin)
        )
        session.commit()
    else:
        session.execute(
            delete(AudiobookRequest).where(
                (col(AudiobookRequest.asin) == asin)
                & (col(AudiobookRequest.user_username) == user.username)
            )
        )
        session.commit()

    results = get_wishlist_results(
        session,
        None if user.is_admin() else user.username,
        "downloaded" if downloaded else "not_downloaded",
    )
    counts = get_wishlist_counts(session, user)

    return template_response(
        "wishlist_page/wishlist.html",
        request,
        user,
        {
            "results": results,
            "page": "downloaded" if downloaded else "wishlist",
            "counts": counts,
            "update_tablist": True,
        },
        block_name="book_wishlist",
    )


@router.get("/manual")
async def read_manual(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(ABRAuth())],
    id: uuid.UUID | None = None,
):
    book = None
    if id:
        book = session.get(ManualBookRequest, id)

    auto_download = quality_config.get_auto_download(session)
    return template_response(
        "manual.html", request, user, {"auto_download": auto_download, "book": book}
    )


@router.post("/manual")
async def add_manual(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    background_task: BackgroundTasks,
    title: Annotated[str, Form()],
    author: Annotated[str, Form()],
    user: Annotated[DetailedUser, Security(ABRAuth())],
    narrator: Annotated[str | None, Form()] = None,
    subtitle: Annotated[str | None, Form()] = None,
    publish_date: Annotated[str | None, Form()] = None,
    info: Annotated[str | None, Form()] = None,
    id: uuid.UUID | None = None,
):
    if id:
        book_request = session.get(ManualBookRequest, id)
        if not book_request:
            raise HTTPException(status_code=404, detail="Book request not found")
        book_request.title = title
        book_request.subtitle = subtitle
        book_request.authors = author.split(",")
        book_request.narrators = narrator.split(",") if narrator else []
        book_request.publish_date = publish_date
        book_request.additional_info = info
    else:
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
    session.commit()

    background_task.add_task(
        send_all_manual_notifications,
        event_type=EventEnum.on_new_request,
        book_request=ManualBookRequest.model_validate(book_request),
    )

    auto_download = quality_config.get_auto_download(session)

    return template_response(
        "manual.html",
        request,
        user,
        {"success": "Successfully added request", "auto_download": auto_download},
        block_name="form",
    )
