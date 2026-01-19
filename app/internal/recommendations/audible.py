import asyncio
import time
from typing import Awaitable
from aiohttp import ClientSession
from pydantic import BaseModel
from sqlmodel import Session, select
from app.internal.models import Audiobook, AudiobookRequest
from app.internal.book_search import (
    REFETCH_TTL,
    CacheResult,
    audible_region_type,
    audible_regions,
    get_book_by_asin,
    get_existing_books,
    get_region_from_settings,
    list_audible_books,
    store_new_books,
)
from app.util.connection import USER_AGENT
from app.util.log import logger


async def list_combined_audible_books(
    session: Session,
    client_session: ClientSession,
    search_terms: list[str],
    num_results: int = 20,
    audible_region: audible_region_type | None = None,
    exclude_requested_username: str | None = None,
) -> list[Audiobook]:
    all_books: list[Audiobook] = []
    books_per_term = max(1, num_results // len(search_terms))

    if exclude_requested_username:
        requested_asins = set(
            session.exec(
                select(AudiobookRequest.asin).where(
                    AudiobookRequest.user_username == exclude_requested_username
                )
            ).all()
        )
    else:
        requested_asins = set[str]()

    for term in search_terms:
        logger.debug("Searching for term", term=term)
        try:
            # Use the existing search function
            term_books = await list_audible_books(
                session=session,
                client_session=client_session,
                query=term,
                num_results=books_per_term,
                page=0,
                audible_region=audible_region,
            )

            # Add unique books only
            for book in term_books:
                if (
                    book.asin not in requested_asins
                    and book not in all_books
                    and len(all_books) < num_results
                ):
                    all_books.append(book)

            logger.debug(
                "Found books for term",
                term=term,
                found=len(term_books),
                total_collected=len(all_books),
            )
            if len(all_books) >= num_results:
                break
        except Exception as e:
            logger.warning("Failed to search for popular term", term=term, error=str(e))
            continue

    logger.info(
        "Fetched popular books using search terms",
        search_terms=search_terms,
        total_found=len(all_books),
    )
    return all_books


async def list_category_audible_books(
    session: Session,
    client_session: ClientSession,
    audible_region: audible_region_type | None = None,
    excluded_requested_username: str | None = None,
) -> dict[str, list[Audiobook]]:
    categories = {
        "trending": ["trending", "viral", "popular now", "hot"],
        "business": [
            "business",
            "entrepreneurship",
            "leadership",
            "productivity",
            "success",
        ],
        "fiction": ["fiction", "novel", "literature", "story", "fantasy", "mystery"],
        "biography": ["biography", "memoir", "autobiography", "life story", "history"],
        "science": ["science", "technology", "physics", "psychology", "innovation"],
        "recent_releases": ["2024", "new release", "latest", "just released"],
    }

    recommendations: dict[str, list[Audiobook]] = {}

    async def _fetch_category(category_name: str):
        books = await list_combined_audible_books(
            session,
            client_session,
            categories[category_name],
            audible_region=audible_region,
            exclude_requested_username=excluded_requested_username,
        )
        recommendations[category_name] = books

    coros: list[Awaitable[None]] = []
    for category_name in categories:
        coros.append(_fetch_category(category_name))
    await asyncio.gather(*coros)
    for book in recommendations.values():
        for b in book:
            session.refresh(b)

    return recommendations


class _AudibleSimsResponse(BaseModel):
    """Used for type-checking audible sims response"""

    class _ProductsItem(BaseModel):
        asin: str | None

    similar_products: list[_ProductsItem] = []


class _SimsCacheKey(BaseModel, frozen=True):
    type: str = "popular"
    region: str
    num_results: int
    asin: str


sims_cache: dict[_SimsCacheKey, CacheResult[list[Audiobook]]] = {}


async def list_similar_audible_books(
    session: Session,
    client_session: ClientSession,
    asin: str,
    num_results: int = 10,
    audible_region: audible_region_type | None = None,
) -> list[Audiobook]:
    """
    Fetch similar/recommended books for a given ASIN using Audible's sims endpoint when available.
    Falls back to author-based search if the endpoint fails or is unavailable.

    Ordering of returned list should match Audible's ordering where possible.
    """
    if audible_region is None:
        audible_region = get_region_from_settings()

    cache_key = _SimsCacheKey(region=audible_region, num_results=num_results, asin=asin)
    cache_result = sims_cache.get(cache_key)
    if cache_result and time.time() - cache_result.timestamp < REFETCH_TTL:
        # Merge cached ORM instances into the current session to avoid cross-session attachment errors
        merged = [session.merge(book) for book in cache_result.value]
        logger.debug("Using cached popular books", region=audible_region)
        return merged

    base_url = f"https://api.audible{audible_regions[audible_region]}/1.0/catalog/products/{asin}/sims"
    params = {"num_results": min(10, max(1, num_results))}  # audible limits to max 10

    ordered: list[Audiobook] = []
    try:
        async with client_session.get(
            base_url, params=params, headers={"User-Agent": USER_AGENT}
        ) as response:
            response.raise_for_status()
            sims = _AudibleSimsResponse.model_validate(await response.json())

        # Extract ASINs in Audible-provided order
        asins = [p.asin for p in sims.similar_products if p.asin]
        if not asins:
            raise ValueError("No sims returned")

        # Reuse existing books from DB cache; then fetch missing via Audimeta/Audnexus
        books_map = get_existing_books(session, set(asins))
        missing_asins = {a for a in asins if a not in books_map.keys()}

        coros = [
            get_book_by_asin(client_session, a, audible_region) for a in missing_asins
        ]
        fetched = await asyncio.gather(*coros)
        for b in fetched:
            if b:
                books_map[b.asin] = b

        store_new_books(session, [b for b in fetched if b])

        for a in asins:
            b = books_map.get(a)
            if b:
                ordered.append(b)

        # Trim to requested size
        ordered = ordered[:num_results]
    except Exception as e:
        # Fallback: approximate with author-based search
        logger.debug(
            "Sims endpoint failed, falling back to author search",
            asin=asin,
            error=str(e),
        )
        try:
            # Find seed book to derive authors
            seed = await get_book_by_asin(client_session, asin, audible_region)
            if seed:
                author = seed.authors[0] if seed.authors else seed.title
                results = await list_audible_books(
                    session=session,
                    client_session=client_session,
                    query=author,
                    num_results=num_results,
                    page=0,
                    audible_region=audible_region,
                )
                # Exclude the seed asin itself
                ordered = [b for b in results if b.asin != asin][:num_results]
            else:
                ordered = []
        except Exception:
            ordered = []

    sims_cache[cache_key] = CacheResult(value=ordered, timestamp=time.time())
    return ordered
