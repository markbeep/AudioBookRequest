import time
from datetime import datetime
from typing import cast

from aiohttp import ClientSession
from pydantic import BaseModel
from sqlalchemy import CursorResult, delete
from sqlmodel import Session, col, not_, select

from app.internal.audible.types import (
    REFETCH_TTL,
    AudibleSearchResponse,
    audible_region_type,
    audible_regions,
    get_region_from_settings,
)
from app.internal.models import Audiobook, AudiobookRequest
from app.util.log import logger


def clear_old_book_caches(session: Session):
    """Deletes outdated cached audiobooks that haven't been requested by anyone"""
    delete_query = delete(Audiobook).where(
        col(Audiobook.updated_at) < datetime.fromtimestamp(time.time() - REFETCH_TTL),
        col(Audiobook.asin).not_in(select(col(AudiobookRequest.asin).distinct())),
        not_(Audiobook.downloaded),
    )
    result = cast(CursorResult[Audiobook], session.execute(delete_query))
    session.commit()
    logger.debug("Cleared old book caches", rowcount=result.rowcount)


class CacheQuery(BaseModel, frozen=True):
    query: str
    num_results: int
    page: int
    audible_region: audible_region_type


class CacheResult[T](BaseModel, frozen=True):
    value: T
    timestamp: float


# simple caching of search results to avoid having to fetch from audible so frequently
search_cache: dict[CacheQuery, CacheResult[list[Audiobook]]] = {}
search_suggestions_cache: dict[str, CacheResult[list[str]]] = {}


class _AudibleSuggestionsResponse(BaseModel):
    """Used for type-checking audible search suggestions response"""

    class _Items(BaseModel):
        class _Item(BaseModel):
            class _Model(BaseModel):
                class _Metadata(BaseModel):
                    class _Title(BaseModel):
                        value: str

                    title: _Title

                class _TitleGroup(BaseModel):
                    class _Title(BaseModel):
                        value: str

                    title: _Title

                product_metadata: _Metadata | None = None
                title_group: _TitleGroup | None = None

                @property
                def title(self) -> str | None:
                    if self.product_metadata and self.product_metadata.title:
                        return self.product_metadata.title.value
                    if self.title_group and self.title_group.title:
                        return self.title_group.title.value
                    return None

            model: _Model

        items: list[_Item]

    model: _Items


async def get_search_suggestions(
    client_session: ClientSession,
    query: str,
    audible_region: audible_region_type | None = None,
) -> list[str]:
    if audible_region is None:
        audible_region = get_region_from_settings()
    cache_result = search_suggestions_cache.get(query)
    if cache_result and time.time() - cache_result.timestamp < REFETCH_TTL:
        return cache_result.value

    base_url = (
        f"https://api.audible{audible_regions[audible_region]}/1.0/searchsuggestions"
    )
    params = {
        "key_strokes": query,
        "site_variant": "desktop",
    }

    try:
        async with client_session.get(
            base_url,
            params=params,
        ) as response:
            response.raise_for_status()
            suggestions = _AudibleSuggestionsResponse.model_validate(
                await response.json()
            )
    except Exception as e:
        logger.error(
            "Exception while fetching search suggestions from Audible",
            query=query,
            region=audible_region,
            error=e,
        )
        return []

    titles = [item.model.title for item in suggestions.model.items if item.model.title]
    search_suggestions_cache[query] = CacheResult(
        value=titles,
        timestamp=time.time(),
    )

    return titles


async def search_audible_books(
    client_session: ClientSession,
    query: str,
    num_results: int = 20,
    page: int = 0,
    audible_region: audible_region_type | None = None,
) -> list[Audiobook]:
    """
    https://audible.readthedocs.io/en/latest/misc/external_api.html#get--1.0-catalog-products

    Use the audible API to fetch all the books. We get all the required metadata by using
    the 'media' response group.
    """
    if audible_region is None:
        audible_region = get_region_from_settings()
    cache_key = CacheQuery(
        query=query,
        num_results=num_results,
        page=page,
        audible_region=audible_region,
    )
    cache_result = search_cache.get(cache_key)

    if cache_result and time.time() - cache_result.timestamp < REFETCH_TTL:
        return cache_result.value

    base_url = (
        f"https://api.audible{audible_regions[audible_region]}/1.0/catalog/products"
    )
    params = {
        "num_results": num_results,
        "products_sort_by": "Relevance",
        "keywords": query,
        "page": page,
        "response_groups": ["media"],
    }

    try:
        async with client_session.get(
            base_url,
            params=params,
        ) as response:
            response.raise_for_status()
            audible_response = AudibleSearchResponse.model_validate(
                await response.json()
            )
    except Exception as e:
        logger.error(
            "Exception while fetching search results from Audible",
            query=query,
            region=audible_region,
            error=e,
        )
        return []

    # do not fetch book results we already have locally
    books = audible_response.audiobooks()

    logger.debug(
        "Search results fetched",
        query=query,
        region=audible_region,
        total_results=len(audible_response.products),
    )

    search_cache[cache_key] = CacheResult(
        value=books,
        timestamp=time.time(),
    )

    # clean up cache slightly
    for k in list(search_cache.keys()):
        if time.time() - search_cache[k].timestamp > REFETCH_TTL:
            try:
                del search_cache[k]
            except KeyError:  # ignore in race conditions
                pass

    return books


def get_existing_books(session: Session, asins: set[str]) -> dict[str, Audiobook]:
    books = session.exec(select(Audiobook).where(col(Audiobook.asin).in_(asins))).all()
    ok_books: list[Audiobook] = []
    for b in books:
        if b.updated_at.timestamp() + REFETCH_TTL < time.time():
            continue
        ok_books.append(b)

    return {b.asin: b for b in ok_books}


# def upsert_new_books(session: Session, books: list[Audiobook]):
#     asins = {b.asin: b for b in books}

#     existing = list(
#         session.exec(
#             select(Audiobook).where(col(Audiobook.asin).in_(asins.keys()))
#         ).all()
#     )

#     to_update: list[Audiobook] = []
#     for b in existing:
#         new_book = asins[b.asin]
#         b.title = new_book.title
#         b.subtitle = new_book.subtitle
#         b.authors = new_book.authors
#         b.narrators = new_book.narrators
#         b.cover_image = new_book.cover_image
#         b.release_date = new_book.release_date
#         b.runtime_length_min = new_book.runtime_length_min
#         to_update.append(b)

#     existing_asins = {b.asin for b in existing}
#     to_add = [b for b in books if b.asin not in existing_asins]

#     logger.info(
#         "Storing new search results in BookRequest cache/db",
#         to_add_count=len(to_add),
#         to_update_count=len(to_update),
#         existing_count=len(existing),
#     )

#     session.add_all(to_add + existing)
#     session.commit()
