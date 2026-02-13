from typing import Annotated

from aiohttp import ClientSession
from fastapi import APIRouter, Depends, Query, Security
from pydantic import BaseModel
from sqlalchemy.sql.functions import count
from sqlmodel import Session, select

from app.internal.audible.types import audible_region_type, get_region_tld_from_settings
from app.internal.auth.authentication import ABRAuth, DetailedUser
from app.internal.models import AudiobookRequest, AudiobookWithRequests
from app.internal.ranking.quality import quality_config
from app.routers.api.recommendations import (
    get_category_recommendations as api_get_category_recommendations,
)
from app.routers.api.recommendations import (
    get_fallback_recommendations as api_get_fallback_recommendations,
)
from app.routers.api.recommendations import (
    get_popular_authors_recommendations as api_get_popular_authors_recommendations,
)
from app.routers.api.recommendations import (
    get_popular_narrators_recommendations as api_get_popular_narrators_recommendations,
)
from app.routers.api.recommendations import (
    get_popular_recommendations as api_get_popular_recommendations,
)
from app.routers.api.recommendations import (
    get_recently_requested_recommendations as api_get_recently_requested_recommendations,
)
from app.routers.api.recommendations import (
    get_user_recommendations as api_get_user_recommendations,
)
from app.util.connection import get_connection
from app.util.db import get_session
from app.util.templates import catalog_response

router = APIRouter()


@router.get("/")
def read_root(
    user: Annotated[DetailedUser, Security(ABRAuth())],
    session: Annotated[Session, Depends(get_session)],
):
    # no need to show the popular tab if there are no requests from other users
    show_popular = (
        0
        < session.exec(
            select(count("*")).where(AudiobookRequest.user_username != user.username)
        ).one()
    )
    return catalog_response(
        "Index.Index",
        user=user,
        region_tld=get_region_tld_from_settings(),
        auto_download=quality_config.get_auto_download(session),
        show_popular=show_popular,
    )


@router.get("/hx-for-you")
async def get_user_recommendations(
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

    return catalog_response(
        "Index.PopularSection",
        title="For You",
        user=user,
        reasons=result.recommendations,
        view_more="/recommendations/for-you",
        description="Personalized recommendations based on your requests",
        empty="No recommendations available at this time. Request some books to start getting recommendations.",
        region_tld=get_region_tld_from_settings(),
        auto_download=quality_config.get_auto_download(session),
    )


@router.get("/hx-popular")
async def get_popular_recommendations(
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

    return catalog_response(
        "Index.PopularSection",
        title="Popular",
        user=user,
        reasons=result,
        description="The most popular books on the instance",
        empty="No popular recommendations available at this time. Request some books to start getting recommendations.",
        region_tld=get_region_tld_from_settings(),
        auto_download=quality_config.get_auto_download(session),
    )


@router.get("/hx-categories")
async def get_category_recommendations(
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

    return catalog_response(
        "Index.Categories",
        categories=result,
        region_tld=get_region_tld_from_settings(),
        auto_start_download=quality_config.get_auto_download(session),
        user=user,
    )


"""

UNUSED ENDPOINTS


"""


class _AudiobookReasonWrapper(BaseModel):
    book: AudiobookWithRequests
    reason: str


@router.get("/hx-recent")
async def get_recently_requested_recommendations(
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

    reasons = [
        _AudiobookReasonWrapper(book=book, reason="Recently requested")
        for book in result
    ]

    return catalog_response(
        "Index.PopularSection",
        reasons=reasons,
        user=user,
        description="Books that have been recently requested by users on the instance",
        empty="No recently requested recommendations available at this time. Request some books to start getting recommendations.",
        region_tld=get_region_tld_from_settings(),
        auto_download=quality_config.get_auto_download(session),
    )


@router.get("/hx-fallback")
async def get_fallback_recommendations(
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

    reasons = [
        _AudiobookReasonWrapper(book=book, reason="Popular on Audible")
        for book in result
    ]

    return catalog_response(
        "Index.PopularSection",
        reasons=reasons,
        user=user,
        description="Popular books from Audible",
        empty="No fallback recommendations available at this time.",
        region_tld=get_region_tld_from_settings(),
        auto_download=quality_config.get_auto_download(session),
    )


@router.get("/hx-authors")
async def get_popular_authors_recommendations(
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

    reasons = [
        _AudiobookReasonWrapper(book=book, reason="Popular author") for book in result
    ]

    return catalog_response(
        "Index.PopularSection",
        reasons=reasons,
        user=user,
        description="Books from popular authors",
        empty="No popular author recommendations available at this time. Request some books to start getting recommendations.",
        region_tld=get_region_tld_from_settings(),
        auto_download=quality_config.get_auto_download(session),
    )


@router.get("/hx-narrators")
async def get_popular_narrators_recommendations(
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

    reasons = [
        _AudiobookReasonWrapper(book=book, reason="Popular narrator") for book in result
    ]

    return catalog_response(
        "Index.PopularSection",
        reasons=reasons,
        user=user,
        description="Books from popular narrators",
        empty="No popular narrator recommendations available at this time. Request some books to start getting recommendations.",
        region_tld=get_region_tld_from_settings(),
        auto_download=quality_config.get_auto_download(session),
    )
