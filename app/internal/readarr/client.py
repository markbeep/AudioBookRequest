from __future__ import annotations

import re

import aiohttp
from aiohttp import ClientSession
from pydantic import TypeAdapter
from sqlmodel import Session, select

from app.internal.audiobookshelf.client import abs_trigger_scan
from app.internal.audiobookshelf.config import abs_config
from app.internal.models import Audiobook
from app.internal.readarr.config import readarr_config
from app.internal.readarr.types import (
    ReadarrAuthorAddOptions,
    ReadarrBook,
    ReadarrBookAddOptions,
    ReadarrMetadataProfile,
    ReadarrQualityProfile,
    ReadarrRootFolder,
    ReadarrSearchResult,
)
from app.util.connection import USER_AGENT
from app.util.db import get_session
from app.util.log import logger

# Extended timeout for Readarr API calls — metadata fetches from Hardcover
# can take 30-180 seconds for new books/authors.
READARR_TIMEOUT = aiohttp.ClientTimeout(total=180)

_SearchResults = TypeAdapter(list[ReadarrSearchResult])
_QualityProfiles = TypeAdapter(list[ReadarrQualityProfile])
_MetadataProfiles = TypeAdapter(list[ReadarrMetadataProfile])
_RootFolders = TypeAdapter(list[ReadarrRootFolder])


def _headers(session: Session) -> dict[str, str]:
    api_key = readarr_config.get_api_key(session)
    assert api_key is not None
    return {"X-Api-Key": api_key, "User-Agent": USER_AGENT}


def _normalize(s: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# ---------------------------------------------------------------------------
# Core search + add flow
# ---------------------------------------------------------------------------


async def _search(
    session: Session, client_session: ClientSession, title: str
) -> list[ReadarrSearchResult]:
    """GET /api/v1/search — returns mixed author/book results."""
    base_url = readarr_config.get_base_url(session)
    if not base_url:
        return []
    url = f"{base_url}/api/v1/search"
    try:
        async with client_session.get(
            url,
            headers=_headers(session),
            params={"term": title},
            timeout=READARR_TIMEOUT,
        ) as resp:
            if not resp.ok:
                logger.error(
                    "Readarr: search failed",
                    status=resp.status,
                    reason=resp.reason,
                )
                return []
            return _SearchResults.validate_python(await resp.json())
    except Exception as e:
        logger.error("Readarr: exception during search", error=str(e))
        return []


async def _add_book(
    session: Session, client_session: ClientSession, book: ReadarrBook
) -> bool:
    """POST /api/v1/book — add a book (and its author if new) to Readarr."""
    base_url = readarr_config.get_base_url(session)
    if not base_url:
        return False
    url = f"{base_url}/api/v1/book"
    try:
        async with client_session.post(
            url,
            headers=_headers(session),
            json=book.model_dump(mode="json"),
            timeout=READARR_TIMEOUT,
        ) as resp:
            if not resp.ok:
                body = await resp.text()
                logger.error(
                    "Readarr: add book failed",
                    status=resp.status,
                    reason=resp.reason,
                    body=body[:500],
                )
                return False
            logger.info(
                "Readarr: book added successfully",
                title=book.title,
                foreignBookId=book.foreignBookId,
            )
            return True
    except Exception as e:
        logger.error("Readarr: exception adding book", error=str(e))
        return False


async def _trigger_book_search(
    session: Session, client_session: ClientSession, book_id: int
) -> bool:
    """POST /api/v1/command — trigger a BookSearch for an existing book."""
    base_url = readarr_config.get_base_url(session)
    if not base_url:
        return False
    url = f"{base_url}/api/v1/command"
    payload = {"name": "BookSearch", "bookIds": [book_id]}
    try:
        async with client_session.post(
            url, headers=_headers(session), json=payload, timeout=READARR_TIMEOUT
        ) as resp:
            if not resp.ok:
                logger.error(
                    "Readarr: trigger search failed",
                    status=resp.status,
                    reason=resp.reason,
                )
                return False
            logger.info("Readarr: search triggered", book_id=book_id)
            return True
    except Exception as e:
        logger.error("Readarr: exception triggering search", error=str(e))
        return False


def _author_matches(book: ReadarrBook, norm_authors: set[str]) -> bool:
    """Check if the book's author matches any of the expected authors."""
    if not book.author:
        return False
    author_name = _normalize(book.author.authorName)
    if not author_name or not norm_authors:
        return False
    return any(a in author_name or author_name in a for a in norm_authors)


def _find_best_book_match(
    results: list[ReadarrSearchResult], audiobook: Audiobook
) -> ReadarrSearchResult | None:
    """Find the best matching book result from mixed search results.

    Multiple books can share the same title (e.g. "Talking to Strangers" by
    Malcolm Gladwell vs Marianne Boucher), so author matching is ALWAYS
    required alongside title matching.
    """
    norm_title = _normalize(audiobook.title)
    norm_authors = {_normalize(a) for a in audiobook.authors}

    # Pass 1: exact title + author match
    for result in results:
        if result.book is None:
            continue
        if _normalize(result.book.title) == norm_title and _author_matches(
            result.book, norm_authors
        ):
            return result

    # Pass 2: title containment (either direction) + author match
    # Handles "Talking to Strangers" matching "Talking to Strangers: What We Should Know..."
    for result in results:
        if result.book is None:
            continue
        result_title = _normalize(result.book.title)
        if (
            norm_title in result_title or result_title in norm_title
        ) and _author_matches(result.book, norm_authors):
            return result

    # Pass 3: author match only (title may differ significantly between Audible and Hardcover)
    for result in results:
        if result.book is None:
            continue
        if _author_matches(result.book, norm_authors):
            return result

    # Pass 4: last resort — exact title match without author (only if we have no author data)
    if not norm_authors:
        for result in results:
            if result.book is None:
                continue
            if _normalize(result.book.title) == norm_title:
                return result

    return None


async def readarr_add_and_search(
    session: Session, client_session: ClientSession, audiobook: Audiobook
) -> bool:
    """
    Main entry point: search Readarr for the book, add it if missing, and
    trigger an indexer search. Returns True on success.
    """
    readarr_config.raise_if_invalid(session)

    # Step 1: Single search call — returns books with full author nested
    results = await _search(session, client_session, audiobook.title)
    if not results:
        logger.warning("Readarr: no search results", title=audiobook.title)
        return False

    # Step 2: Find best matching book result
    book_match = _find_best_book_match(results, audiobook)
    if not book_match or not book_match.book:
        logger.warning("Readarr: no matching book", title=audiobook.title)
        return False

    book = book_match.book

    # Step 3: If book already in Readarr, just trigger search
    if book.id > 0:
        logger.info("Readarr: book exists, triggering search", book_id=book.id)
        return await _trigger_book_search(session, client_session, book.id)

    # Step 4: Add book — set config fields on the author object
    author = book.author
    if not author or not author.foreignAuthorId:
        logger.error(
            "Readarr: search result missing author data",
            title=book.title,
        )
        return False

    author.qualityProfileId = readarr_config.get_quality_profile_id(session)
    author.metadataProfileId = readarr_config.get_metadata_profile_id(session)
    author.rootFolderPath = readarr_config.get_root_folder_path(session)
    author.monitored = True
    author.addOptions = ReadarrAuthorAddOptions(
        monitor="all",
        searchForMissingBooks=False,
    )

    book.monitored = True
    book.addOptions = ReadarrBookAddOptions(
        searchForNewBook=True,
    )

    return await _add_book(session, client_session, book)


async def background_readarr_add_and_search(asin: str) -> None:
    """Background task wrapper for readarr_add_and_search.

    On success, marks matching books as downloaded and triggers an ABS
    library scan so new media is picked up quickly.
    """
    with next(get_session()) as session:
        async with ClientSession(
            timeout=aiohttp.ClientTimeout(total=300)
        ) as client_session:
            audiobook = session.get(Audiobook, asin)
            if not audiobook:
                logger.warning("Readarr background: book not found", asin=asin)
                return
            logger.info("Readarr background: starting add+search", asin=asin)
            success = await readarr_add_and_search(session, client_session, audiobook)
            logger.info("Readarr background: complete", asin=asin, success=success)
            if success:
                same_books = session.exec(
                    select(Audiobook).where(Audiobook.asin == asin)
                ).all()
                for b in same_books:
                    b.downloaded = True
                    session.add(b)
                session.commit()
                try:
                    if abs_config.is_valid(session):
                        await abs_trigger_scan(session, client_session)
                except Exception:
                    pass


# ---------------------------------------------------------------------------
# Settings helpers — used by the settings page to populate dropdowns
# ---------------------------------------------------------------------------


async def readarr_get_quality_profiles(
    session: Session, client_session: ClientSession
) -> list[ReadarrQualityProfile]:
    base_url = readarr_config.get_base_url(session)
    if not base_url:
        return []
    url = f"{base_url}/api/v1/qualityprofile"
    try:
        async with client_session.get(
            url, headers=_headers(session), timeout=READARR_TIMEOUT
        ) as resp:
            if not resp.ok:
                return []
            return _QualityProfiles.validate_python(await resp.json())
    except Exception:
        return []


async def readarr_get_metadata_profiles(
    session: Session, client_session: ClientSession
) -> list[ReadarrMetadataProfile]:
    base_url = readarr_config.get_base_url(session)
    if not base_url:
        return []
    url = f"{base_url}/api/v1/metadataprofile"
    try:
        async with client_session.get(
            url, headers=_headers(session), timeout=READARR_TIMEOUT
        ) as resp:
            if not resp.ok:
                return []
            return _MetadataProfiles.validate_python(await resp.json())
    except Exception:
        return []


async def readarr_get_root_folders(
    session: Session, client_session: ClientSession
) -> list[ReadarrRootFolder]:
    base_url = readarr_config.get_base_url(session)
    if not base_url:
        return []
    url = f"{base_url}/api/v1/rootfolder"
    try:
        async with client_session.get(
            url, headers=_headers(session), timeout=READARR_TIMEOUT
        ) as resp:
            if not resp.ok:
                return []
            return _RootFolders.validate_python(await resp.json())
    except Exception:
        return []
