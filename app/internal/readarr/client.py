from __future__ import annotations

import re
from typing import Any

import aiohttp
from aiohttp import ClientSession
from sqlmodel import Session

from app.internal.models import Audiobook
from app.internal.readarr.config import readarr_config
from app.util.connection import USER_AGENT
from app.util.db import get_session
from app.util.log import logger

# Extended timeout for Readarr API calls — metadata fetches from Hardcover
# can take 30-180 seconds for new books/authors.
READARR_TIMEOUT = aiohttp.ClientTimeout(total=180)


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
) -> list[dict[str, Any]]:
    """GET /api/v1/search — returns mixed author/book results with full author nested in books."""
    base_url = readarr_config.get_base_url(session)
    if not base_url:
        return []
    url = f"{base_url}/api/v1/search"
    try:
        async with client_session.get(
            url, headers=_headers(session), params={"term": title}, timeout=READARR_TIMEOUT
        ) as resp:
            if not resp.ok:
                logger.error(
                    "Readarr: search failed",
                    status=resp.status,
                    reason=resp.reason,
                )
                return []
            return await resp.json()
    except Exception as e:
        logger.error("Readarr: exception during search", error=str(e))
        return []


async def _add_book(
    session: Session, client_session: ClientSession, book_data: dict[str, Any]
) -> bool:
    """POST /api/v1/book — add a book (and its author if new) to Readarr."""
    base_url = readarr_config.get_base_url(session)
    if not base_url:
        return False
    url = f"{base_url}/api/v1/book"
    try:
        async with client_session.post(
            url, headers=_headers(session), json=book_data, timeout=READARR_TIMEOUT
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
                title=book_data.get("title"),
                foreignBookId=book_data.get("foreignBookId"),
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


def _author_matches(
    book: dict[str, Any], norm_authors: set[str]
) -> bool:
    """Check if the book's author matches any of the expected authors."""
    author_name = _normalize(book.get("author", {}).get("authorName", ""))
    if not author_name or not norm_authors:
        return False
    return any(a in author_name or author_name in a for a in norm_authors)


def _find_best_book_match(
    results: list[dict[str, Any]], audiobook: Audiobook
) -> dict[str, Any] | None:
    """Find the best matching book result from mixed search results.

    Multiple books can share the same title (e.g. "Talking to Strangers" by
    Malcolm Gladwell vs Marianne Boucher), so author matching is ALWAYS
    required alongside title matching.
    """
    norm_title = _normalize(audiobook.title)
    norm_authors = {_normalize(a) for a in audiobook.authors}

    # Filter to book results only (skip author-only results)
    book_results = [r for r in results if "book" in r and r["book"]]

    # Pass 1: exact title + author match
    for result in book_results:
        book = result["book"]
        if _normalize(book.get("title", "")) == norm_title and _author_matches(book, norm_authors):
            return result

    # Pass 2: title containment (either direction) + author match
    # Handles "Talking to Strangers" matching "Talking to Strangers: What We Should Know..."
    for result in book_results:
        book = result["book"]
        result_title = _normalize(book.get("title", ""))
        if (norm_title in result_title or result_title in norm_title) and _author_matches(book, norm_authors):
            return result

    # Pass 3: author match only (title may differ significantly between Audible and Hardcover)
    for result in book_results:
        book = result["book"]
        if _author_matches(book, norm_authors):
            return result

    # Pass 4: last resort — exact title match without author (only if we have no author data)
    if not norm_authors:
        for result in book_results:
            book = result["book"]
            if _normalize(book.get("title", "")) == norm_title:
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
    if not book_match:
        logger.warning("Readarr: no matching book", title=audiobook.title)
        return False

    book = book_match["book"]

    # Step 3: If book already in Readarr, just trigger search
    if book.get("id") and book["id"] > 0:
        logger.info("Readarr: book exists, triggering search", book_id=book["id"])
        return await _trigger_book_search(session, client_session, book["id"])

    # Step 4: Add book — set config fields on the author object (pyarr pattern)
    author = book.get("author")
    if not author or not author.get("foreignAuthorId"):
        logger.error(
            "Readarr: search result missing author data",
            title=book.get("title"),
        )
        return False

    author["qualityProfileId"] = readarr_config.get_quality_profile_id(session)
    author["metadataProfileId"] = readarr_config.get_metadata_profile_id(session)
    author["rootFolderPath"] = readarr_config.get_root_folder_path(session)
    author["monitored"] = True
    author["addOptions"] = {
        "monitor": "all",
        "searchForMissingBooks": False,
    }

    book["monitored"] = True
    book["addOptions"] = {
        "searchForNewBook": readarr_config.get_search_on_add(session),
    }

    return await _add_book(session, client_session, book)


async def background_readarr_add_and_search(asin: str) -> None:
    """Background task wrapper for readarr_add_and_search."""
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
            logger.info(
                "Readarr background: complete", asin=asin, success=success
            )


# ---------------------------------------------------------------------------
# Settings helpers — used by the settings page to populate dropdowns
# ---------------------------------------------------------------------------


async def readarr_get_quality_profiles(
    session: Session, client_session: ClientSession
) -> list[dict[str, Any]]:
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
            return await resp.json()
    except Exception:
        return []


async def readarr_get_metadata_profiles(
    session: Session, client_session: ClientSession
) -> list[dict[str, Any]]:
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
            return await resp.json()
    except Exception:
        return []


async def readarr_get_root_folders(
    session: Session, client_session: ClientSession
) -> list[dict[str, Any]]:
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
            return await resp.json()
    except Exception:
        return []
