from typing import Annotated

from aiohttp import ClientSession
from fastapi import APIRouter, Depends, Query, Request, Security
from sqlmodel import Session

from app.internal.auth.authentication import ABRAuth, DetailedUser
from app.internal.book_search import audible_region_type
from app.routers.api.recommendations import (
    get_user_recommendations as api_get_user_recommendations,
    get_popular_recommendations as api_get_popular_recommendations,
    get_recently_requested_recommendations as api_get_recently_requested_recommendations,
    get_fallback_recommendations as api_get_fallback_recommendations,
    get_category_recommendations as api_get_category_recommendations,
    get_popular_authors_recommendations as api_get_popular_authors_recommendations,
    get_popular_narrators_recommendations as api_get_popular_narrators_recommendations,
)
from app.util.connection import get_connection
from app.util.db import get_session
from app.util.templates import template_response

router = APIRouter(prefix="/recommendations")


@router.get("/user")
async def get_user_recommendations(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    user: Annotated[DetailedUser, Security(ABRAuth())],
    seed_asins: Annotated[list[str] | None, Query(alias="seed_asins")] = None,
    limit: int = 20,
):
    result = await api_get_user_recommendations(
        session=session,
        client_session=client_session,
        user=user,
        seed_asins=seed_asins,
        limit=limit,
    )
    return template_response(
        "root.html",
        request,
        user,
        {"for_you": result.recommendations},
        block_name="for_you",
    )


@router.get("/for-you")
async def get_for_you_recommendations(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    user: Annotated[DetailedUser, Security(ABRAuth())],
    page: int = 1,
    per_page: int = 10,
):
    result = await api_get_user_recommendations(
        session=session,
        client_session=client_session,
        user=user,
        limit=per_page,
        offset=(page - 1) * per_page,
    )
    has_next = result.total > page * per_page

    return template_response(
        "recommendations/for_you.html",
        request,
        user,
        {
            "recommendations": result.recommendations,
            "page": page,
            "per_page": per_page,
            "has_next": has_next,
            "total_items": result.total,
        },
    )


@router.get("/popular")
async def get_popular_recommendations(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(ABRAuth())],
    min_requests: int = 1,
    limit: int = 10,
    exclude_downloaded: bool = True,
):
    result = await api_get_popular_recommendations(
        session=session,
        user=user,
        min_requests=min_requests,
        limit=limit,
        exclude_downloaded=exclude_downloaded,
    )
    return template_response(
        "root.html",
        request,
        user,
        {"popular": result},
        block_name="popular",
    )


@router.get("/recent")
async def get_recently_requested_recommendations(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(ABRAuth())],
    limit: int = 10,
    days_back: int = 30,
    exclude_downloaded: bool = True,
):
    result = await api_get_recently_requested_recommendations(
        session=session,
        user=user,
        limit=limit,
        days_back=days_back,
        exclude_downloaded=exclude_downloaded,
    )
    return template_response(
        "root.html",
        request,
        user,
        {"recently_requested": result},
        block_name="recently_requested",
    )


@router.get("/fallback")
async def get_fallback_recommendations(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    user: Annotated[DetailedUser, Security(ABRAuth())],
    limit: int = 10,
    audible_region: audible_region_type | None = None,
):
    """Get fallback popular recommendations from Audible search. Does not take into account user history or preference."""

    result = await api_get_fallback_recommendations(
        session=session,
        client_session=client_session,
        user=user,
        limit=limit,
        audible_region=audible_region,
    )
    return template_response(
        "root.html",
        request,
        user,
        {"fallback": result},
        block_name="fallback",
    )


@router.get("/categories")
async def get_category_recommendations(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    user: Annotated[DetailedUser, Security(ABRAuth())],
    audible_region: audible_region_type | None = None,
):
    result = await api_get_category_recommendations(
        session=session,
        client_session=client_session,
        user=user,
        audible_region=audible_region,
    )
    return template_response(
        "root.html",
        request,
        user,
        {"categories": result},
        block_name="categories",
    )


@router.get("/authors")
async def get_popular_authors_recommendations(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    user: Annotated[DetailedUser, Security(ABRAuth())],
    limit: int = 10,
    exclude_downloaded: bool = True,
    audible_region: audible_region_type | None = None,
    personal_favorites: bool = True,
):
    result = await api_get_popular_authors_recommendations(
        session=session,
        client_session=client_session,
        user=user,
        limit=limit,
        exclude_downloaded=exclude_downloaded,
        audible_region=audible_region,
        personal_favorites=personal_favorites,
    )
    return template_response(
        "root.html",
        request,
        user,
        {"popular_authors": result},
        block_name="popular_authors",
    )


@router.get("/narrators")
async def get_popular_narrators_recommendations(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    user: Annotated[DetailedUser, Security(ABRAuth())],
    limit: int = 10,
    exclude_downloaded: bool = True,
    audible_region: audible_region_type | None = None,
    personal_favorites: bool = True,
):
    result = await api_get_popular_narrators_recommendations(
        session=session,
        client_session=client_session,
        user=user,
        limit=limit,
        exclude_downloaded=exclude_downloaded,
        audible_region=audible_region,
        personal_favorites=personal_favorites,
    )
    return template_response(
        "root.html",
        request,
        user,
        {"popular_narrators": result},
        block_name="popular_narrators",
    )
