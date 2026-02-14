import html
import json
import posixpath
import time
from datetime import datetime
from typing import Literal
from urllib.parse import urlencode

from aiohttp import ClientResponse, ClientSession
from pydantic import BaseModel, TypeAdapter
from sqlmodel import Session
from torf import BdecodeError, MetainfoError, ReadError, Torrent

from app.internal.indexers.abstract import SessionContainer
from app.internal.models import (
    Audiobook,
    EventEnum,
    Indexer,
    ManualBookRequest,
    ProwlarrSource,
    TorrentSource,
    UsenetSource,
    User,
)
from app.internal.notifications import send_all_notifications
from app.internal.prowlarr.source_metadata import edit_source_metadata
from app.internal.prowlarr.util import (
    prowlarr_config,
    prowlarr_indexer_cache,
    prowlarr_source_cache,
)
from app.util.connection import USER_AGENT
from app.util.log import logger


async def _get_torrent_info_hash(
    client_session: ClientSession, download_url: str
) -> str | None:
    logger.debug("Fetching torrent info hash", download_url=download_url)
    async with client_session.get(
        download_url, headers={"User-Agent": USER_AGENT}
    ) as r:
        if not r.ok:
            logger.error("Failed to fetch torrent", download_url=download_url)
            return None
        content = await r.read()
        try:
            tor = Torrent.read_stream(content)
            return tor.infohash
        except (MetainfoError, ReadError, BdecodeError) as e:
            logger.error(
                "Error reading torrent info hash",
                download_url=download_url,
                error=str(e),
            )


async def start_download(
    session: Session,
    client_session: ClientSession,
    guid: str,
    indexer_id: int,
    requester: User,
    book_asin: str,
    prowlarr_source: ProwlarrSource | None = None,
) -> ClientResponse:
    prowlarr_config.raise_if_invalid(session)
    base_url = prowlarr_config.get_base_url(session)
    api_key = prowlarr_config.get_api_key(session)
    assert base_url is not None and api_key is not None

    url = posixpath.join(base_url, "api/v1/search")
    logger.debug("Starting download", guid=guid)
    headers = {"X-Api-Key": api_key, "User-Agent": USER_AGENT}

    async with client_session.post(
        url,
        json={"guid": guid, "indexerId": indexer_id},
        headers=headers,
    ) as response:
        if not response.ok:
            logger.error(
                "Failed to start download",
                guid=guid,
                response=response,
                text=await response.text(),
            )
            await send_all_notifications(
                EventEnum.on_failed_download,
                requester,
                book_asin,
                {
                    "errorStatus": str(response.status),
                    "errorReason": response.reason or "<unknown>",
                },
            )
            return response

        # Find additional metadata/replacements to pass along notifications
        additional_replacements: dict[str, str] = {"bookASIN": book_asin}
        if prowlarr_source:
            if prowlarr_source.download_url and prowlarr_source.protocol == "torrent":
                if info_hash := await _get_torrent_info_hash(
                    client_session, prowlarr_source.download_url
                ):
                    additional_replacements["torrentInfoHash"] = info_hash
            elif prowlarr_source.magnet_url and prowlarr_source.protocol == "torrent":
                info_hash = prowlarr_source.magnet_url.replace("magnet:?", "")
                info_hash = info_hash.replace("xt=urn:btih:", "")
                info_hash = info_hash.split("&")[0]
                additional_replacements["torrentInfoHash"] = info_hash

            additional_replacements["sourceSizeMB"] = str(prowlarr_source.size_MB)
            additional_replacements["sourceTitle"] = prowlarr_source.title
            additional_replacements["indexerName"] = prowlarr_source.indexer
            additional_replacements["sourceProtocol"] = prowlarr_source.protocol

        logger.debug("Download successfully started", guid=guid)
        await send_all_notifications(
            EventEnum.on_successful_download,
            requester,
            book_asin,
            additional_replacements,
        )

        return response


class _ProwlarrResultBase(BaseModel):
    guid: str
    indexerId: int
    indexer: str
    title: str
    size: int
    infoUrl: str | None = None
    indexerFlags: list[str] = []
    downloadUrl: str | None = None
    magnetUrl: str | None = None
    publishDate: str


class _ProwlarrTorrentResult(_ProwlarrResultBase):
    protocol: Literal["torrent"]
    seeders: int = 0
    leechers: int = 0


class _ProwlarrUsenetResult(_ProwlarrResultBase):
    protocol: Literal["usenet"]
    grabs: int = 0


_ProwlarrSearchResult = TypeAdapter(
    list[_ProwlarrTorrentResult | _ProwlarrUsenetResult]
)


async def query_prowlarr(
    session: Session,
    client_session: ClientSession,
    book: Audiobook | ManualBookRequest,
    indexer_ids: list[int] | None = None,
    force_refresh: bool = False,
    only_return_if_cached: bool = False,
) -> list[ProwlarrSource] | None:
    query = book.title

    base_url = prowlarr_config.get_base_url(session)
    api_key = prowlarr_config.get_api_key(session)
    assert base_url is not None and api_key is not None
    source_ttl = prowlarr_config.get_source_ttl(session)

    if only_return_if_cached:
        cached_sources = prowlarr_source_cache.get(source_ttl, query)
        return cached_sources

    if not force_refresh:
        cached_sources = prowlarr_source_cache.get(source_ttl, query)
        if cached_sources:
            return cached_sources

    params: dict[str, int | str | list[int]] = {
        "query": query,
        "type": "search",
        "limit": 100,
        "offset": 0,
    }

    if len(x := prowlarr_config.get_categories(session)) > 0:
        params["categories"] = x

    if indexer_ids is not None:
        params["indexerIds"] = indexer_ids

    url = posixpath.join(base_url, f"api/v1/search?{urlencode(params, doseq=True)}")

    logger.info("Querying prowlarr", url=url)
    start_time = time.time()
    prowlarr_text = None

    try:
        async with client_session.get(
            url,
            headers={
                "X-Api-Key": api_key,
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
            },
        ) as response:
            prowlarr_text = await response.text()
            if not response.ok:
                logger.error(
                    "Prowlarr: Failed to query", response=await response.text()
                )
                return []
            search_results = _ProwlarrSearchResult.validate_python(
                await response.json()
            )
    except TimeoutError as e:
        elapsed_time = time.time() - start_time
        logger.error(
            "Prowlarr query timed out", error=str(e), elapsed_time=elapsed_time
        )
        return []
    except Exception as e:
        elapsed_time = time.time() - start_time
        logger.error(
            "Failed to query Prowlarr",
            error=str(e),
            prowlarr_response=prowlarr_text,
            elapsed_time=elapsed_time,
        )
        return []

    elapsed_time = time.time() - start_time
    logger.info(
        "Prowlarr query completed",
        elapsed_time_seconds=elapsed_time,
        results_size=len(search_results),
    )

    sources: list[ProwlarrSource] = []
    for result in search_results:
        try:
            if result.protocol not in ["torrent", "usenet"]:
                logger.info(
                    "Skipping source with unknown protocol", protocol=result.protocol
                )
                continue
            if result.protocol == "torrent":
                sources.append(
                    TorrentSource(
                        protocol="torrent",
                        guid=result.guid,
                        indexer_id=result.indexerId,
                        indexer=result.indexer,
                        title=result.title,
                        seeders=result.seeders,
                        leechers=result.leechers,
                        size=result.size,
                        info_url=result.infoUrl,
                        indexer_flags=[x.lower() for x in result.indexerFlags],
                        download_url=result.downloadUrl,
                        magnet_url=result.magnetUrl,
                        publish_date=datetime.fromisoformat(result.publishDate),
                    )
                )
            else:
                sources.append(
                    UsenetSource(
                        protocol="usenet",
                        guid=result.guid,
                        indexer_id=result.indexerId,
                        indexer=result.indexer,
                        title=result.title,
                        grabs=result.grabs,
                        size=result.size,
                        info_url=result.infoUrl,
                        indexer_flags=[x.lower() for x in result.indexerFlags],
                        download_url=result.downloadUrl,
                        magnet_url=result.magnetUrl,
                        publish_date=datetime.fromisoformat(result.publishDate),
                    )
                )
        except KeyError as e:
            logger.error("Failed to parse source", source=result, keyerror=str(e))

    # add additional metadata using any available indexers
    container = SessionContainer(session=session, client_session=client_session)
    await edit_source_metadata(book, sources, container)

    prowlarr_source_cache.set(sources, query)

    return sources


class IndexerResponse(BaseModel):
    indexers: dict[int, Indexer] = {}
    state: Literal["ok", "missingUrlKey", "failedFetch"]
    error: str | None = None

    @property
    def json_string(self) -> str:
        return html.escape(
            json.dumps(
                {id: indexer.model_dump() for id, indexer in self.indexers.items()}
            )
        )

    @property
    def ok(self) -> bool:
        return self.state == "ok"


_IndexerList = TypeAdapter(list[Indexer])


async def get_indexers(
    session: Session, client_session: ClientSession
) -> IndexerResponse:
    """Fetch the list of all indexers from Prowlarr."""
    base_url = prowlarr_config.get_base_url(session)
    api_key = prowlarr_config.get_api_key(session)
    source_ttl = prowlarr_config.get_source_ttl(session)

    if not base_url or not api_key:
        logger.warning("Prowlarr base url or api key not set, skipping indexer fetch")
        return IndexerResponse(
            state="failedFetch",
            error="Missing Prowlarr base url or api key",
        )

    indexers = list(prowlarr_indexer_cache.get_all(source_ttl).values())
    try:
        if len(indexers) > 0:
            return IndexerResponse(
                indexers={indexer.id: indexer for indexer in indexers},
                state="ok",
            )

        url = posixpath.join(base_url, "api/v1/indexer")
        logger.info("Fetching indexers from Prowlarr", url=url)

        async with client_session.get(
            url,
            headers={"X-Api-Key": api_key, "User-Agent": USER_AGENT},
        ) as response:
            if not response.ok:
                logger.error("Failed to fetch indexers", response=response)
                return IndexerResponse(
                    state="failedFetch",
                    error=f"{response.status}: {response.reason}",
                )

            indexers = _IndexerList.validate_python(await response.json())
            for indexer in indexers:
                prowlarr_indexer_cache.set(indexer, str(indexer.id))
            logger.info(
                "Successfully fetched indexers from Prowlarr",
                count=len(indexers),
            )

        return IndexerResponse(
            indexers={
                indexer.id: indexer
                for indexer in prowlarr_indexer_cache.get_all(source_ttl).values()
            },
            state="ok",
        )
    except Exception as e:
        logger.error("Failed to access Prowlarr to fetch indexers", error=str(e))
        return IndexerResponse(
            state="failedFetch",
            error=str(e),
        )
