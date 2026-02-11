import time

from aiohttp import ClientSession
from pydantic import BaseModel
from sqlmodel import Session

from app.internal.audible.search import CacheResult, search_audible_books
from app.internal.audible.single import get_single_book
from app.internal.audible.types import (
    REFETCH_TTL,
    AudibleSimilarResponse,
    audible_region_type,
    audible_regions,
    get_region_from_settings,
)
from app.internal.models import Audiobook
from app.util.log import logger


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
    params = {
        "num_results": min(10, max(1, num_results)),  # audible limits to max 10
        "response_groups": ["media"],
    }

    ordered: list[Audiobook] = []
    try:
        async with client_session.get(base_url, params=params) as response:
            response.raise_for_status()
            sims = AudibleSimilarResponse.model_validate(await response.json())

        ordered = sims.audiobooks()
    except Exception as e:
        # Fallback: approximate with author-based search
        logger.debug(
            "Sims endpoint failed, falling back to author search",
            asin=asin,
            error=str(e),
        )
        try:
            # Find seed book to derive authors
            seed = session.get(Audiobook, asin)
            if not seed:
                try:
                    seed = await get_single_book(client_session, asin, audible_region)
                except Exception as e:
                    logger.error(
                        "Failed to fetch seed book for sims fallback",
                        asin=asin,
                        error=str(e),
                    )
                    seed = None

            if seed:
                author = seed.authors[0] if seed.authors else seed.title
                results = await search_audible_books(
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
