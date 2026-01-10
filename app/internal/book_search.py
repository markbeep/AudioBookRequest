import asyncio
import time
from datetime import datetime
from typing import Literal, Optional, TypedDict, cast
from urllib.parse import urlencode

from aiohttp import ClientSession
from pydantic import BaseModel
from sqlalchemy import CursorResult, delete
from sqlalchemy.exc import InvalidRequestError
from sqlmodel import Session, col, not_, select

from app.internal.env_settings import Settings
from app.internal.models import Audiobook, AudiobookRequest
from app.util.log import logger

REFETCH_TTL = 60 * 60 * 24 * 7  # 1 week

audible_region_type = Literal[
    "us",
    "ca",
    "uk",
    "au",
    "fr",
    "de",
    "jp",
    "it",
    "in",
    "es",
    "br",
]
audible_regions: dict[audible_region_type, str] = {
    "us": ".com",
    "ca": ".ca",
    "uk": ".co.uk",
    "au": ".com.au",
    "fr": ".fr",
    "de": ".de",
    "jp": ".co.jp",
    "it": ".it",
    "in": ".in",
    "es": ".es",
    "br": ".com.br",
}


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


def get_region_from_settings() -> audible_region_type:
    region = Settings().app.default_region
    if region not in audible_regions:
        return "us"
    return region


class _AudnexusResponse(BaseModel):
    class _Author(TypedDict):
        name: str

    asin: str
    title: str
    subtitle: Optional[str]
    authors: list[_Author]
    narrators: list[_Author]
    image: Optional[str]
    releaseDate: str
    runtimeLengthMin: int


async def _get_audnexus_book(
    session: ClientSession,
    asin: str,
    region: audible_region_type,
) -> Optional[Audiobook]:
    """
    https://audnex.us/#tag/Books/operation/getBookById
    """
    logger.debug("Fetching book from Audnexus", asin=asin, region=region)
    try:
        async with session.get(
            f"https://api.audnex.us/books/{asin}?region={region}",
            headers={"Client-Agent": "audiobookrequest"},
        ) as response:
            if not response.ok:
                logger.warning(
                    "Failed to fetch book from Audnexus",
                    asin=asin,
                    status=response.status,
                    reason=response.reason,
                )
                return None
            audnexus_response = _AudnexusResponse.model_validate(await response.json())
    except Exception as e:
        logger.error("Exception while fetching book from Audnexus", asin=asin, error=e)
        return None
    return Audiobook(
        asin=audnexus_response.asin,
        title=audnexus_response.title,
        subtitle=audnexus_response.subtitle,
        authors=[author["name"] for author in audnexus_response.authors],
        narrators=[narrator["name"] for narrator in audnexus_response.narrators],
        cover_image=audnexus_response.image,
        release_date=datetime.fromisoformat(audnexus_response.releaseDate),
        runtime_length_min=audnexus_response.runtimeLengthMin,
    )


class _AudimetaResponse(BaseModel):
    class _Author(TypedDict):
        name: str

    asin: str
    title: str
    subtitle: Optional[str]
    authors: list[_Author]
    narrators: list[_Author]
    imageUrl: Optional[str]
    releaseDate: str
    lengthMinutes: Optional[int]


async def _get_audimeta_book(
    session: ClientSession,
    asin: str,
    region: audible_region_type,
) -> Optional[Audiobook]:
    """
    https://audimeta.de/api-docs/#/book/get_book__asin_
    """
    logger.debug("Fetching book from Audimeta", asin=asin, region=region)
    try:
        async with session.get(
            f"https://audimeta.de/book/{asin}?region={region}",
            headers={"Client-Agent": "audiobookrequest"},
        ) as response:
            if not response.ok:
                logger.warning(
                    "Failed to fetch book from Audimeta",
                    asin=asin,
                    status=response.status,
                    reason=response.reason,
                )
                return None
            audimeta_response = _AudimetaResponse.model_validate(await response.json())
    except Exception as e:
        logger.error("Exception while fetching book from Audimeta", asin=asin, error=e)
        return None
    return Audiobook(
        asin=audimeta_response.asin,
        title=audimeta_response.title,
        subtitle=audimeta_response.subtitle,
        authors=[author["name"] for author in audimeta_response.authors],
        narrators=[narrator["name"] for narrator in audimeta_response.narrators],
        cover_image=audimeta_response.imageUrl,
        release_date=datetime.fromisoformat(audimeta_response.releaseDate),
        runtime_length_min=audimeta_response.lengthMinutes or 0,
    )


async def get_book_by_asin(
    session: ClientSession,
    asin: str,
    audible_region: audible_region_type | None = None,
) -> Optional[Audiobook]:
    if audible_region is None:
        audible_region = get_region_from_settings()
    book = await _get_audimeta_book(session, asin, audible_region)
    if book:
        return book
    logger.debug(
        "Audimeta did not have the book, trying Audnexus",
        asin=asin,
        region=audible_region,
    )
    book = await _get_audnexus_book(session, asin, audible_region)
    if book:
        return book
    logger.warning(
        "Did not find the book on both Audnexus and Audimeta",
        asin=asin,
        region=audible_region,
    )


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

    params = {
        "key_strokes": query,
        "site_variant": "desktop",
    }
    base_url = (
        f"https://api.audible{audible_regions[audible_region]}/1.0/searchsuggestions?"
    )
    url = base_url + urlencode(params)

    try:
        async with client_session.get(url) as response:
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


class _AudibleSearchResponse(BaseModel):
    class _AsinObj(BaseModel):
        asin: str

    products: list[_AsinObj]


async def list_audible_books(
    session: Session,
    client_session: ClientSession,
    query: str,
    num_results: int = 20,
    page: int = 0,
    audible_region: audible_region_type | None = None,
) -> list[Audiobook]:
    """
    https://audible.readthedocs.io/en/latest/misc/external_api.html#get--1.0-catalog-products

    We first use the audible search API to get a list of matching ASINs. Using these ASINs we check our database
    if we have any of the books already to save on the amount of requests we have to do.
    Any books we don't already have locally, we fetch all the details from audnexus.
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
        try:
            for book in cache_result.value:
                # add back books to the session so we can access their attributes
                session.add(book)
                session.refresh(book)
            logger.debug(
                "Using cached search result", query=query, region=audible_region
            )
            return cache_result.value
        except InvalidRequestError:
            logger.debug(
                "Cached search result contained deleted book, refetching",
                query=query,
                region=audible_region,
            )

    params = {
        "num_results": num_results,
        "products_sort_by": "Relevance",
        "keywords": query,
        "page": page,
    }
    base_url = (
        f"https://api.audible{audible_regions[audible_region]}/1.0/catalog/products?"
    )
    url = base_url + urlencode(params)

    try:
        async with client_session.get(url) as response:
            response.raise_for_status()
            audible_response = _AudibleSearchResponse.model_validate(
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
    asins = set(asin_obj.asin for asin_obj in audible_response.products)
    books = get_existing_books(session, asins)
    for key in books.keys():
        asins.remove(key)

    # book ASINs we do not have => fetch and store
    coros = [get_book_by_asin(client_session, asin, audible_region) for asin in asins]
    new_books = await asyncio.gather(*coros)
    new_books = [b for b in new_books if b]

    store_new_books(session, new_books)

    for b in new_books:
        books[b.asin] = b

    ordered: list[Audiobook] = []
    for asin_obj in audible_response.products:
        book = books.get(asin_obj.asin)
        if book:
            ordered.append(book)

    search_cache[cache_key] = CacheResult(
        value=ordered,
        timestamp=time.time(),
    )

    # clean up cache slightly
    for k in list(search_cache.keys()):
        if time.time() - search_cache[k].timestamp > REFETCH_TTL:
            try:
                del search_cache[k]
            except KeyError:  # ignore in race conditions
                pass

    return ordered


def get_existing_books(session: Session, asins: set[str]) -> dict[str, Audiobook]:
    books = list(
        session.exec(select(Audiobook).where(col(Audiobook.asin).in_(asins))).all()
    )

    ok_books: list[Audiobook] = []
    for b in books:
        if b.updated_at.timestamp() + REFETCH_TTL < time.time():
            continue
        ok_books.append(b)

    return {b.asin: b for b in ok_books}


def store_new_books(session: Session, books: list[Audiobook]):
    asins = {b.asin: b for b in books}

    existing = list(
        session.exec(
            select(Audiobook).where(col(Audiobook.asin).in_(asins.keys()))
        ).all()
    )

    to_update: list[Audiobook] = []
    for b in existing:
        new_book = asins[b.asin]
        b.title = new_book.title
        b.subtitle = new_book.subtitle
        b.authors = new_book.authors
        b.narrators = new_book.narrators
        b.cover_image = new_book.cover_image
        b.release_date = new_book.release_date
        b.runtime_length_min = new_book.runtime_length_min
        to_update.append(b)

    existing_asins = {b.asin for b in existing}
    to_add = [b for b in books if b.asin not in existing_asins]

    logger.info(
        "Storing new search results in BookRequest cache/db",
        to_add_count=len(to_add),
        to_update_count=len(to_update),
        existing_count=len(existing),
    )

    session.add_all(to_add + existing)
    session.commit()
