from __future__ import annotations

import asyncio
import posixpath
import re
from datetime import datetime
from typing import Literal

from aiohttp import ClientSession
from pydantic import BaseModel, TypeAdapter
from sqlmodel import Session

from app.internal.audiobookshelf.config import abs_config
from app.internal.audiobookshelf.types import (
    ABSBookItem,
    ABSBookItemMinified,
    ABSLibrary,
    ABSPodcastItem,
)
from app.internal.models import Audiobook
from app.util.connection import USER_AGENT
from app.util.db import get_session
from app.util.log import logger


def _headers(session: Session) -> dict[str, str]:
    token = abs_config.get_api_token(session)
    assert token is not None
    return {"Authorization": f"Bearer {token}", "User-Agent": USER_AGENT}


class _LibraryArray(BaseModel):
    libraries: list[ABSLibrary] = []


async def abs_get_libraries(
    session: Session, client_session: ClientSession
) -> list[ABSLibrary]:
    base_url = abs_config.get_base_url(session)
    if not base_url:
        return []
    url = posixpath.join(base_url, "api/libraries")
    try:
        async with client_session.get(url, headers=_headers(session)) as resp:
            if not resp.ok:
                logger.error(
                    "ABS: failed to fetch libraries",
                    status=resp.status,
                    reason=resp.reason,
                )
                return []
            data = _LibraryArray.model_validate(await resp.json())
            return data.libraries
    except Exception as e:
        logger.error("ABS: exception fetching libraries", error=str(e))
        return []


async def abs_trigger_scan(session: Session, client_session: ClientSession) -> bool:
    base_url = abs_config.get_base_url(session)
    lib_id = abs_config.get_library_id(session)
    if not base_url or not lib_id:
        return False
    url = posixpath.join(base_url, f"api/libraries/{lib_id}/scan")
    logger.debug("ABS: triggering library scan", library_id=lib_id, url=url)
    async with client_session.post(url, headers=_headers(session), json={}) as resp:
        if not resp.ok:
            logger.warning(
                "ABS: failed to trigger scan", status=resp.status, reason=resp.reason
            )
            return False
        return True


async def background_abs_trigger_scan():
    with next(get_session()) as session:
        async with ClientSession() as client_session:
            logger.debug("ABS: running background library scan trigger")
            success = await abs_trigger_scan(session, client_session)
            logger.info(
                "ABS: background library scan trigger complete", success=success
            )


class _ListResponseBook(BaseModel):
    results: list[ABSBookItemMinified] = []
    mediaType: Literal["book"]


class _ListResponsePodcast(BaseModel):
    results: list[ABSPodcastItem] = []
    mediaType: Literal["podcast"]


_ListResponse: TypeAdapter[_ListResponseBook | _ListResponsePodcast] = TypeAdapter(
    _ListResponseBook | _ListResponsePodcast
)


async def abs_list_library_items(
    session: Session,
    client_session: ClientSession,
    limit: int = 10,
) -> list[Audiobook]:
    """
    Fetch a page of items from the configured ABS library and map them to Audiobook objects to render on the homepage
    """
    base_url = abs_config.get_base_url(session)
    lib_id = abs_config.get_library_id(session)
    if not base_url or not lib_id:
        return []

    url = posixpath.join(base_url, f"api/libraries/{lib_id}/items")
    params = {
        "limit": str(limit),
        "page": "0",
        "minified": "1",
        "sort": "addedAt",
        "desc": "1",
    }

    try:
        async with client_session.get(
            url, headers=_headers(session), params=params
        ) as resp:
            if not resp.ok:
                logger.debug(
                    "ABS: failed to list library items",
                    status=resp.status,
                    reason=resp.reason,
                )
                return []
            payload = _ListResponse.validate_python(await resp.json())
            if payload.mediaType == "podcast":
                logger.warning(
                    "ABS: podcasts not supported in library listing", lib_id=lib_id
                )
                return []
    except Exception as e:
        logger.debug("ABS: exception listing library items", error=str(e))
        return []

    results = payload.results
    books: list[Audiobook] = []
    for item in results:
        try:
            metadata = item.media.metadata
            title = metadata.title
            subtitle = metadata.subtitle
            authors = [metadata.authorName]
            narrators = [metadata.narratorName]
            # Cover: ABS exposes cover via /api/items/:id/cover
            cover_image = posixpath.join(base_url, f"api/items/{item.id}/cover")
            # Duration in seconds -> minutes
            try:
                runtime_length_min = int(round(item.media.duration / 60))
            except Exception:
                runtime_length_min = 0

            if metadata.publishedDate:
                try:
                    # Try ISO format
                    release_date = datetime.fromisoformat(
                        metadata.publishedDate.replace("Z", "+00:00")
                    )
                except Exception:
                    release_date = datetime.now()
            else:
                release_date = datetime.now()

            if not metadata.asin or not title:
                logger.warning(
                    "ABS: skipping library item with missing ASIN or title",
                    item_id=item.id,
                    asin=metadata.asin,
                    title=title,
                )
                continue

            book = Audiobook(
                asin=metadata.asin,
                title=title,
                subtitle=subtitle,
                authors=authors,
                narrators=narrators,
                cover_image=cover_image,
                release_date=release_date,
                runtime_length_min=runtime_length_min,
                downloaded=True,
            )
            books.append(book)
        except Exception as e:
            logger.debug("ABS: failed to map library item", error=str(e))

    return books


class _BookSearchResult(BaseModel):
    class _LibraryItem(BaseModel):
        libraryItem: ABSBookItem

    book: list[_LibraryItem] | None = None


async def _abs_search(
    session: Session, client_session: ClientSession, query: str
) -> list[ABSBookItem]:
    base_url = abs_config.get_base_url(session)
    lib_id = abs_config.get_library_id(session)
    if not base_url or not lib_id:
        return []
    url = posixpath.join(base_url, f"api/libraries/{lib_id}/search")
    try:
        async with client_session.get(
            url, headers=_headers(session), params={"q": query}
        ) as resp:
            if not resp.ok:
                logger.debug(
                    "ABS: search failed", status=resp.status, reason=resp.reason
                )
                return []
            data = _BookSearchResult.model_validate(await resp.json())
            if data.book is None:
                logger.warning(
                    "ABS: search returned no book results", query=query, lib_id=lib_id
                )
                return []
            return [it.libraryItem for it in data.book]
    except Exception as e:
        logger.debug("ABS: exception during search", error=str(e))
        return []


def _normalize(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


async def abs_book_exists(
    session: Session,
    client_session: ClientSession,
    book: Audiobook,
) -> bool:
    """
    Heuristic check if a book exists in ABS library by searching by ASIN and title/author.
    """
    # Try ASIN first
    candidates: list[ABSBookItem] = []
    if book.asin:
        candidates = await _abs_search(session, client_session, book.asin)
        logger.debug(
            "ABS: ASIN search results",
            asin=book.asin,
            candidate_count=len(candidates),
        )
    if not candidates:
        logger.debug(
            "ABS: ASIN search yielded no results. Checking with title",
            asin=book.asin,
        )
        q = f"{book.title}".strip()
        candidates = await _abs_search(session, client_session, q)

    if not candidates:
        return False

    norm_title = _normalize(book.title)
    norm_authors = {_normalize(a) for a in book.authors}

    for it in candidates:
        # ABS search returns different shapes, try best-effort
        title = it.media.metadata.title
        if not title:
            logger.debug("ABS: search result missing title", item=it)
            continue
        authors = it.media.metadata.authors
        if _normalize(title) == norm_title:
            if not norm_authors or any(
                _normalize(a.name) in norm_authors for a in authors
            ):
                return True
    return False


async def abs_mark_downloaded_flags(
    session: Session,
    client_session: ClientSession,
    books: list[Audiobook],
) -> None:
    if not abs_config.get_check_downloaded(session):
        return
    # Only check books not already marked downloaded
    to_check = [b for b in books if not b.downloaded]
    # Limit to avoid flooding ABS
    to_check = to_check[:25]

    async def _check_and_mark(b: Audiobook):
        try:
            exists = await abs_book_exists(session, client_session, b)
            logger.debug("ABS: exist check", asin=b.asin, exists=exists)
            if exists:
                b.downloaded = True
                session.add(b)
        except Exception as e:
            logger.debug("ABS: failed exist check", asin=b.asin, error=str(e))

    await asyncio.gather(*[_check_and_mark(b) for b in to_check])
    session.commit()
