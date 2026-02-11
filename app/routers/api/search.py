from typing import Annotated

from aiohttp import ClientSession
from fastapi import APIRouter, Depends, HTTPException, Query, Security

from app.internal.audible.search import get_search_suggestions, search_audible_books
from app.internal.audible.types import (
    audible_region_type,
    audible_regions,
    get_region_from_settings,
)
from app.internal.auth.authentication import AnyAuth, DetailedUser
from app.internal.models import AudiobookWithRequests
from app.util.connection import get_connection

router = APIRouter(prefix="/search", tags=["Search"])


@router.get("", response_model=list[AudiobookWithRequests])
async def search_books(
    client_session: Annotated[ClientSession, Depends(get_connection)],
    user: Annotated[DetailedUser, Security(AnyAuth())],
    query: Annotated[str | None, Query(alias="q")] = None,
    num_results: int = 20,
    page: int = 0,
    region: audible_region_type | None = None,
):
    if region is None:
        region = get_region_from_settings()
    if audible_regions.get(region) is None:
        raise HTTPException(status_code=400, detail="Invalid region")
    if query:
        results = await search_audible_books(
            client_session=client_session,
            query=query,
            num_results=num_results,
            page=page,
            audible_region=region,
        )
    else:
        results = []

    return [
        AudiobookWithRequests(
            book=book,
            requests=book.requests,
            username=user.username,
        )
        for book in results
    ]


@router.get("/suggestions", response_model=list[str])
async def search_suggestions(
    query: Annotated[str, Query(alias="q")],
    _: Annotated[DetailedUser, Security(AnyAuth())],
    region: audible_region_type | None = None,
):
    if region is None:
        region = get_region_from_settings()
    async with ClientSession() as client_session:
        return await get_search_suggestions(client_session, query, region)
