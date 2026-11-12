import uuid
from contextlib import contextmanager
from typing import Literal

import aiohttp
import pydantic
from aiohttp import ClientSession
from fastapi import HTTPException
from sqlmodel import Session

from app.internal.audiobookshelf.client import abs_trigger_scan
from app.internal.audiobookshelf.config import abs_config
from app.internal.chaptarr.client import ChaptarrError, start_chaptarr_download
from app.internal.chaptarr.config import chaptarr_config
from app.internal.download_backend import get_download_backend
from app.internal.models import Audiobook, ManualBookRequest, ProwlarrSource
from app.internal.prowlarr.prowlarr import (
    DownloadFailed,
    query_prowlarr,
    start_download,
)
from app.internal.prowlarr.util import prowlarr_config
from app.internal.ranking.download_ranking import rank_sources
from app.util.db import get_session
from app.util.log import logger

querying: set[str] = set()


@contextmanager
def manage_queried(asin_or_uuid: str):
    querying.add(asin_or_uuid)
    try:
        yield
    finally:
        try:
            querying.remove(asin_or_uuid)
        except KeyError:
            pass


class QueryResult(pydantic.BaseModel):
    sources: list[ProwlarrSource] | None
    book: Audiobook | ManualBookRequest
    state: Literal["ok", "querying", "uncached"]
    error_message: str | None = None

    @property
    def ok(self) -> bool:
        return self.state == "ok"


async def query_sources(
    asin_or_uuid: str,
    session: Session,
    client_session: ClientSession,
    force_refresh: bool = False,
    start_auto_download: bool = False,
    only_return_if_cached: bool = False,
) -> QueryResult:
    # First check if the asin_or_uuid is a UUID (manual request)
    try:
        uuid_obj = uuid.UUID(asin_or_uuid)
        book = session.get(ManualBookRequest, uuid_obj)
    except ValueError:
        # Standard Audiobook ASIN
        book = session.get(Audiobook, asin_or_uuid)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if asin_or_uuid in querying:
        return QueryResult(
            sources=None,
            book=book,
            state="querying",
        )

    with manage_queried(asin_or_uuid):
        # Chaptarr owns download, import and file organization when selected.
        if (
            start_auto_download
            and not book.fulfilled
            and isinstance(book, Audiobook)
            and get_download_backend(session) == "chaptarr"
        ):
            if not chaptarr_config.is_valid(session):
                raise HTTPException(
                    status_code=400, detail="Chaptarr is not configured"
                )
            try:
                await start_chaptarr_download(session, client_session, book)
            except ChaptarrError as e:
                raise HTTPException(status_code=500, detail=e.message) from e
            try:
                if abs_config.is_valid(session):
                    await abs_trigger_scan(session, client_session)
            except Exception:
                logger.error("Failed to trigger ABS scan after starting download")
            return QueryResult(sources=None, book=book, state="ok")

        if get_download_backend(session) == "chaptarr":
            raise HTTPException(
                status_code=400,
                detail="Sources require the Prowlarr download backend",
            )

        prowlarr_config.raise_if_invalid(session)

        sources = await query_prowlarr(
            session,
            client_session,
            book,
            force_refresh=force_refresh,
            only_return_if_cached=only_return_if_cached,
            indexer_ids=prowlarr_config.get_indexers(session),
        )
        if sources is None:
            return QueryResult(
                sources=None,
                book=book,
                state="uncached",
            )

        is_manual = isinstance(book, ManualBookRequest)
        ranked = await rank_sources(session, client_session, sources, book, is_manual)

        # start download if requested
        if start_auto_download and not book.fulfilled and len(ranked) > 0:
            try:
                await start_download(
                    session=session,
                    client_session=client_session,
                    guid=ranked[0].guid,
                    indexer_id=ranked[0].indexer_id,
                    asin_or_uuid=asin_or_uuid,
                    prowlarr_source=ranked[0],
                )
            except DownloadFailed as e:
                raise HTTPException(status_code=500, detail=e.message) from e

            # Try to trigger an ABS scan to pick up new media
            try:
                if abs_config.is_valid(session):
                    await abs_trigger_scan(session, client_session)
            except Exception:
                logger.error("Failed to trigger ABS scan after starting download")

        return QueryResult(
            sources=ranked,
            book=book,
            state="ok",
        )


async def background_start_query(asin_or_uuid: str, auto_download: bool):
    # Runs after the response is sent; a raise here aborts the ASGI request
    # context ("response already started"), so every failure is logged instead.
    try:
        with next(get_session()) as session:
            async with ClientSession(
                timeout=aiohttp.ClientTimeout(60)
            ) as client_session:
                await query_sources(
                    asin_or_uuid=asin_or_uuid,
                    session=session,
                    client_session=client_session,
                    start_auto_download=auto_download,
                )
    except HTTPException as e:
        logger.error(
            "Background query failed",
            asin_or_uuid=asin_or_uuid,
            status=e.status_code,
            error=e.detail,
        )
    except Exception as e:
        logger.error("Background query failed", asin_or_uuid=asin_or_uuid, error=str(e))
