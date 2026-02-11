from typing import Annotated, Sequence

from aiohttp import ClientSession
from fastapi import APIRouter, Depends, Query, Security
from sqlmodel import Session

from app.internal.audible.category import (
    list_category_audible_books,
    list_combined_audible_books,
)
from app.internal.audible.types import audible_region_type, get_region_from_settings
from app.internal.auth.authentication import AnyAuth, DetailedUser
from app.internal.models import Audiobook, AudiobookWithRequests
from app.internal.recommendations.local import (
    AudiobookPopularity,
    get_most_popular_authors,
    get_popular_books,
    get_recently_requested_books,
)
from app.internal.recommendations.user_recommendations import (
    UserSimsRecommendation,
    get_user_sims_recommendations,
)
from app.util.connection import get_connection
from app.util.db import get_session

router = APIRouter(prefix="/recommendations", tags=["Recommendations"])


@router.get("/user", response_model=UserSimsRecommendation)
async def get_user_recommendations(
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    user: Annotated[DetailedUser, Security(AnyAuth())],
    seed_asins: Annotated[list[str] | None, Query(alias="seed_asins")] = None,
    limit: int = 20,
    offset: int = 0,
) -> UserSimsRecommendation:
    recommendations = await get_user_sims_recommendations(
        session=session,
        client_session=client_session,
        user=user,
        seed_asins=seed_asins,
        limit=limit,
        offset=offset,
    )
    return recommendations


@router.get("/popular", response_model=list[AudiobookPopularity])
async def get_popular_recommendations(
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(AnyAuth())],
    min_requests: int = 1,
    limit: int = 10,
    exclude_downloaded: bool = True,
) -> list[AudiobookPopularity]:
    return get_popular_books(
        session=session,
        limit=limit,
        min_requests=min_requests,
        exclude_downloaded=exclude_downloaded,
        exclude_requested_username=user.username,
    )


@router.get("/recent", response_model=Sequence[Audiobook])
async def get_recently_requested_recommendations(
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(AnyAuth())],
    limit: int = 10,
    days_back: int = 30,
    exclude_downloaded: bool = True,
) -> Sequence[AudiobookWithRequests]:
    return get_recently_requested_books(
        session=session,
        limit=limit,
        days_back=days_back,
        exclude_downloaded=exclude_downloaded,
        exclude_requested_username=user.username,
    )


@router.get("/fallback", response_model=list[Audiobook])
async def get_fallback_recommendations(
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    user: Annotated[DetailedUser, Security(AnyAuth())],
    limit: int = 10,
    audible_region: audible_region_type | None = None,
) -> list[AudiobookWithRequests]:
    """Get fallback popular recommendations from Audible search. Does not take into account user history or preference."""

    if audible_region is None:
        audible_region = get_region_from_settings()

    popular_search_terms = [
        "bestseller",
        "james clear",
        "atomic habits",
        "stephen king",
        "psychology",
        "biography",
        "business",
        "self help",
    ]
    return await list_combined_audible_books(
        session=session,
        client_session=client_session,
        search_terms=popular_search_terms,
        num_results=limit,
        audible_region=audible_region,
        exclude_requested_username=user.username,
    )


@router.get("/categories", response_model=dict[str, list[Audiobook]])
async def get_category_recommendations(
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    user: Annotated[DetailedUser, Security(AnyAuth())],
    audible_region: audible_region_type | None = None,
) -> dict[str, list[AudiobookWithRequests]]:
    """Get recommendations by popular categories from Audible search."""

    if audible_region is None:
        audible_region = get_region_from_settings()

    return await list_category_audible_books(
        session=session,
        client_session=client_session,
        audible_region=audible_region,
        excluded_requested_username=user.username,
    )


@router.get("/authors", response_model=list[AudiobookWithRequests])
async def get_popular_authors_recommendations(
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    user: Annotated[DetailedUser, Security(AnyAuth())],
    limit: int = 10,
    exclude_downloaded: bool = True,
    audible_region: audible_region_type | None = None,
    personal_favorites: bool = True,
) -> list[AudiobookWithRequests]:
    if audible_region is None:
        audible_region = get_region_from_settings()

    author_narrators = get_most_popular_authors(
        session=session,
        limit=limit,
        exclude_downloaded=exclude_downloaded,
        username=user.username if personal_favorites else None,
    )
    return await list_combined_audible_books(
        session=session,
        client_session=client_session,
        search_terms=author_narrators.authors,
        num_results=limit,
        audible_region=audible_region,
    )


@router.get("/narrators", response_model=list[Audiobook])
async def get_popular_narrators_recommendations(
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    user: Annotated[DetailedUser, Security(AnyAuth())],
    limit: int = 10,
    exclude_downloaded: bool = True,
    audible_region: audible_region_type | None = None,
    personal_favorites: bool = True,
) -> list[AudiobookWithRequests]:
    if audible_region is None:
        audible_region = get_region_from_settings()

    author_narrators = get_most_popular_authors(
        session=session,
        limit=limit,
        exclude_downloaded=exclude_downloaded,
        username=user.username if personal_favorites else None,
    )
    return await list_combined_audible_books(
        session=session,
        client_session=client_session,
        search_terms=author_narrators.narrators,
        num_results=limit,
        audible_region=audible_region,
    )
