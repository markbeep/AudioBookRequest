import asyncio
from typing import Awaitable

from aiohttp import ClientSession
from sqlmodel import Session, select

from app.internal.audible.search import search_audible_books
from app.internal.audible.types import audible_region_type
from app.internal.models import Audiobook, AudiobookRequest, AudiobookWithRequests
from app.util.log import logger


async def list_combined_audible_books(
    session: Session,
    client_session: ClientSession,
    search_terms: list[str],
    num_results: int = 20,
    audible_region: audible_region_type | None = None,
    exclude_requested_username: str | None = None,
) -> list[AudiobookWithRequests]:
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
            term_books = await search_audible_books(
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
    books = [
        AudiobookWithRequests(
            book=book,
            requests=book.requests,
            username=exclude_requested_username,
        )
        for book in all_books
    ]

    return books


async def list_category_audible_books(
    session: Session,
    client_session: ClientSession,
    audible_region: audible_region_type | None = None,
    excluded_requested_username: str | None = None,
) -> dict[str, list[AudiobookWithRequests]]:
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

    recommendations: dict[str, list[AudiobookWithRequests]] = {}

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

    for _, v in recommendations.items():
        for b in v:
            for r in b.book.requests:
                session.refresh(r)

    return recommendations
