import uuid
from contextlib import contextmanager
from typing import Literal

import aiohttp
import pydantic
from aiohttp import ClientSession
from fastapi import HTTPException
from sqlmodel import Session, select

from app.internal.audiobookshelf.client import abs_trigger_scan
from app.internal.audiobookshelf.config import abs_config
from app.internal.models import Audiobook, ManualBookRequest, ProwlarrSource, User
from app.internal.prowlarr.prowlarr import query_prowlarr, start_download
from app.internal.prowlarr.util import prowlarr_config
from app.internal.ranking.download_ranking import rank_sources
from app.util.db import get_session

querying: set[str] = set()


@contextmanager
def manage_queried(asin: str):
    querying.add(asin)
    try:
        yield
    finally:
        try:
            querying.remove(asin)
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
    asin: str,
    session: Session,
    client_session: ClientSession,
    requester: User,
    force_refresh: bool = False,
    start_auto_download: bool = False,
    only_return_if_cached: bool = False,
) -> QueryResult:
    # First check if the ASIN is a UUID (manual request)
    try:
        uuid_obj = uuid.UUID(asin)
        book = session.get(ManualBookRequest, uuid_obj)
    except ValueError:
        # Standard Audiobook ASIN
        book = session.exec(select(Audiobook).where(Audiobook.asin == asin)).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if asin in querying:
        return QueryResult(
            sources=None,
            book=book,
            state="querying",
        )

    with manage_queried(asin):
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

        # start download if requested
        if start_auto_download and not book.downloaded and len(ranked) > 0:
            resp = await start_download(
                session=session,
                client_session=client_session,
                guid=ranked[0].guid,
                indexer_id=ranked[0].indexer_id,
                requester=requester,
                book_asin=asin,
                prowlarr_source=ranked[0],
            )
            if resp.ok:
                same_books = session.exec(
                    select(Audiobook).where(Audiobook.asin == asin)
                ).all()
                for b in same_books:
                    b.downloaded = True
                    session.add(b)
                session.commit()
                # Try to trigger an ABS scan to pick up new media
                try:
                    if abs_config.is_valid(session):
                        await abs_trigger_scan(session, client_session)
                except Exception:
                    pass
            else:
                raise HTTPException(status_code=500, detail="Failed to start download")

        return QueryResult(
            sources=ranked,
            book=book,
            state="ok",
        )


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
