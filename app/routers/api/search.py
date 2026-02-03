from typing import Annotated

from aiohttp import ClientSession
from fastapi import APIRouter, Depends, HTTPException, Query, Security
from pydantic import BaseModel
from sqlmodel import Session

from app.internal import book_search
from app.internal.auth.authentication import AnyAuth, DetailedUser
from app.internal.book_search import (
    audible_region_type,
    audible_regions,
    clear_old_book_caches,
    get_region_from_settings,
    list_audible_books,
)
from app.internal.models import Audiobook, AudiobookRequest
from app.util.connection import get_connection
from app.util.db import get_session

router = APIRouter(prefix="/search", tags=["Search"])


class AudiobookSearchResult(BaseModel):
    book: Audiobook
    requests: list[AudiobookRequest]
    username: str

    @property
    def already_requested(self):
        if self.username:
            return any(req.user_username == self.username for req in self.requests)
        return len(self.requests) > 0


@router.get("", response_model=list[AudiobookSearchResult])
async def search_books(
    client_session: Annotated[ClientSession, Depends(get_connection)],
    session: Annotated[Session, Depends(get_session)],
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

    return [
        AudiobookSearchResult(
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
        return await book_search.get_search_suggestions(client_session, query, region)
