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
    Response,
    Security,
)
from htpy.starlette import HtpyResponse
from sqlmodel import Session

from app.components.book_card import book_card
from app.internal.auth.authentication import ABRAuth, DetailedUser
from app.internal.book_search import (
    audible_region_type,
    audible_regions,
    get_region_from_settings,
)
from app.internal.models import (
    Audiobook,
    GroupEnum,
    ManualBookRequest,
)
from app.internal.prowlarr.util import prowlarr_config
from app.internal.ranking.quality import quality_config
from app.internal.db_queries import get_wishlist_results, get_wishlist_counts
from app.util.connection import get_connection
from app.util.db import get_session
from app.util.log import logger
from app.util.templates import template_response
from app.routers.api.search import (
    search_books,
    search_suggestions as api_search_suggestions,
)
from app.routers.api.requests import (
    create_request,
    delete_request as api_delete_request,
    create_manual_request,
    ManualRequest,
    update_manual_request,
)

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
    if region is None:
        region = get_region_from_settings()
    try:
        results = await search_books(
            client_session=client_session,
            session=session,
            user=user,
            query=query,
            num_results=num_results,
            page=page,
            region=region,
        )

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
    suggestions = await api_search_suggestions(query, user, region)
    return template_response(
        "search.html",
        request,
        user,
        {"suggestions": suggestions},
        block_name="search_suggestions",
    )


@router.post("/hx/request/{asin}")
async def add_request_hx(
    request: Request,
    asin: str,
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    background_task: BackgroundTasks,
    user: Annotated[DetailedUser, Security(ABRAuth())],
    query: Annotated[str | None, Form()] = None,
    page: Annotated[int, Form()] = 0,
    region: Annotated[audible_region_type | None, Form()] = None,
    num_results: Annotated[int, Form()] = 20,
):
    await add_request(
        request,
        asin=asin,
        session=session,
        client_session=client_session,
        background_task=background_task,
        user=user,
        query=query,
        page=page,
        region=region,
        num_results=num_results,
    )

    book = session.get(Audiobook, asin)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    return HtpyResponse(
        book_card(
            book=book,
            already_requested=True,
            auto_download_enabled=quality_config.get_auto_download(session),
            user=user,
        )
    )


@router.post("/request/{asin}")
async def add_request(
    request: Request,
    asin: str,
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    background_task: BackgroundTasks,
    user: Annotated[DetailedUser, Security(ABRAuth())],
    query: Annotated[str | None, Form()] = None,
    page: Annotated[int, Form()] = 0,
    region: Annotated[audible_region_type | None, Form()] = None,
    num_results: Annotated[int, Form()] = 20,
):
    try:
        await create_request(
            asin=asin,
            session=session,
            client_session=client_session,
            background_task=background_task,
            user=user,
            region=region,
        )
    except HTTPException as e:
        logger.warning(
            e.detail,
            username=user.username,
            asin=asin,
        )

    results = []
    if query:
        results = await search_books(
            client_session=client_session,
            session=session,
            user=user,
            query=query,
            num_results=num_results,
            page=page,
            region=region,
        )

    prowlarr_configured = prowlarr_config.is_valid(session)

    if query is None:
        # TODO: hacky way to refresh requests added to recommendations
        return Response(status_code=204, headers={"HX-Refresh": "true"})

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
    await api_delete_request(asin, session, user)

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
    req_body = ManualRequest(
        title=title,
        author=author,
        narrator=narrator,
        subtitle=subtitle,
        publish_date=publish_date,
        info=info,
    )
    if id:
        await update_manual_request(id, req_body, session, user)
    else:
        await create_manual_request(req_body, session, background_task, user)

    auto_download = quality_config.get_auto_download(session)

    return template_response(
        "manual.html",
        request,
        user,
        {"success": "Successfully added request", "auto_download": auto_download},
        block_name="form",
    )
