import asyncio
from typing import Literal

import aiohttp
import pydantic
from aiohttp import ClientSession
from fastapi import HTTPException
from sqlmodel import Session, select

from app.internal.env_settings import Settings
from app.internal.models import Audiobook, AudiobookRequest, ProwlarrSource, User
from app.internal.prowlarr.prowlarr import query_prowlarr, start_download
from app.internal.prowlarr.util import prowlarr_config
from app.internal.ranking.download_ranking import rank_sources
from app.util.db import get_session
from app.util.log import logger

_query_locks: dict[str, asyncio.Lock] = {}
settings = Settings()


def _get_query_lock(asin: str) -> asyncio.Lock:
    lock = _query_locks.get(asin)
    if lock is None:
        lock = asyncio.Lock()
        _query_locks[asin] = lock
    return lock


async def _try_acquire(lock: asyncio.Lock) -> bool:
    try:
        await asyncio.wait_for(lock.acquire(), timeout=0.001)
        return True
    except TimeoutError:
        return False


class QueryResult(pydantic.BaseModel):
    sources: list[ProwlarrSource] | None
    book: Audiobook
    state: Literal["ok", "querying", "uncached"]
    error_message: str | None = None

    @property
    def ok(self) -> bool:
        return self.state == "ok"


async def query_sources(
    asin: str,
    session: Session,
    client_session: ClientSession,
    requester: User,
    force_refresh: bool = False,
    start_auto_download: bool = False,
    only_return_if_cached: bool = False,
) -> QueryResult:
    book = session.exec(select(Audiobook).where(Audiobook.asin == asin)).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    lock = _get_query_lock(asin)
    if not await _try_acquire(lock):
        return QueryResult(sources=None, book=book, state="querying")

    try:
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

        ranked = await rank_sources(session, client_session, sources, book)

        # Handle auto-download
        if start_auto_download and len(ranked) > 0:
            book_request = session.exec(
                select(AudiobookRequest).where(
                    AudiobookRequest.asin == asin,
                    AudiobookRequest.downloaded.is_(False),
                    AudiobookRequest.user_username == requester.username,
                )
            ).first()

            if not book_request:
                logger.warning(
                    "No active AudiobookRequest found for auto-download",
                    asin=asin,
                    username=requester.username,
                )
                raise HTTPException(
                    status_code=404,
                    detail="No active AudiobookRequest found for auto-download.",
                )

            success = await start_download(  # start_download now returns bool
                session=session,
                client_session=client_session,
                guid=ranked[0].guid,
                indexer_id=ranked[0].indexer_id,
                requester=requester,
                audiobook_request=book_request,  # Pass the AudiobookRequest object
                prowlarr_source=ranked[0],  # prowlarr_source is now required
            )

            if not success:
                raise HTTPException(status_code=500, detail="Failed to start download")

        return QueryResult(
            sources=ranked,
            book=book,
            state="ok",
        )
    finally:
        lock.release()


async def background_start_query(asin: str, requester: User, auto_download: bool):
    with next(get_session()) as session:
        async with ClientSession(timeout=aiohttp.ClientTimeout(60)) as client_session:
            await query_sources(
                asin=asin,
                session=session,
                client_session=client_session,
                start_auto_download=auto_download,
                requester=requester,
            )
