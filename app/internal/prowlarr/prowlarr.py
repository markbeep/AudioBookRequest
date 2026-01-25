import html
import json
import posixpath
from datetime import datetime
import time
from typing import Literal
from urllib.parse import urlencode

from aiohttp import ClientSession
from pydantic import BaseModel, TypeAdapter
from sqlmodel import Session
from torf import BdecodeError, MetainfoError, ReadError, Torrent

from app.internal.indexers.abstract import SessionContainer
from app.internal.models import (
    Audiobook,
    Indexer,
    ProwlarrSource,
    TorrentSource,
    UsenetSource,
    User,
    AudiobookRequest,  # Import AudiobookRequest
)
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
    audiobook_request: AudiobookRequest,  # Changed from book_asin: str
    prowlarr_source: ProwlarrSource,  # Now required to be present
) -> bool:  # Now returns only bool, as it only attempts direct qBittorrent
    from app.internal.download_clients.config import download_client_config
    from app.internal.download_clients.qbittorrent import QbittorrentClient

    qbit_enabled = download_client_config.get_qbit_enabled(session)

    if not qbit_enabled:
        logger.error("qBittorrent is not enabled, cannot start direct download")
        return False

    if not prowlarr_source:
        logger.error("No prowlarr_source provided for direct qBittorrent download")
        return False

    client = QbittorrentClient(session)
    success = False
    info_hash = None  # Initialize info_hash

    if prowlarr_source.magnet_url:
        success = await client.add_torrent(
            prowlarr_source.magnet_url,
            is_magnet=True,
            tags=[f"asin:{audiobook_request.asin}"],
        )
        if success:
            import re

            # Extract hash from magnet link
            match = re.search(
                r"xt=urn:btih:([a-zA-Z0-9]+)", prowlarr_source.magnet_url, re.IGNORECASE
            )
            if match:
                info_hash = match.group(1).lower()
            else:
                # Fallback or error logging?
                # If we can't extract hash, we might not be able to track it.
                # But it was added to client.
                logger.warning(
                    "Could not extract hash from magnet link",
                    magnet=prowlarr_source.magnet_url,
                )
                info_hash = None
    elif prowlarr_source.download_url:
        # We need to fetch the torrent file content
        fetch_headers = {"User-Agent": USER_AGENT}
        fetch_cookies = {}

        # If it's a MAM URL, we need to add the session cookie
        if "myanonamouse.net" in prowlarr_source.download_url:
            from app.internal.indexers.mam import MamIndexer
            from app.internal.indexers.configuration import create_valued_configuration
            from app.internal.indexers.abstract import SessionContainer

            config_obj = await MamIndexer.get_configurations(
                SessionContainer(session=session, client_session=client_session)
            )
            valued = create_valued_configuration(config_obj, session)
            mam_session_id = str(getattr(valued, "mam_session_id") or "")
            if mam_session_id:
                if mam_session_id.startswith("mam_id="):
                    mam_session_id = mam_session_id[7:]
                fetch_cookies["mam_id"] = mam_session_id

        async with client_session.get(
            prowlarr_source.download_url, headers=fetch_headers, cookies=fetch_cookies
        ) as r:
            if r.ok:
                content = await r.read()
                success = await client.add_torrent(
                    content, is_magnet=False, tags=[f"asin:{audiobook_request.asin}"]
                )
                if success:
                    info_hash = await _get_torrent_info_hash(
                        client_session, prowlarr_source.download_url
                    )
            else:
                logger.error(
                    "Failed to fetch torrent file for direct qBit download",
                    url=prowlarr_source.download_url,
                    status=r.status,
                )
    else:
        logger.error(
            "Prowlarr source has no magnet or download URL for direct qBittorrent download",
            guid=guid,
        )
        return False

    if success:
        logger.debug("Download successfully started via direct qBittorrent")
        # Update AudiobookRequest with download info
        audiobook_request.torrent_hash = info_hash
        audiobook_request.download_state = "queued"
        audiobook_request.download_progress = 0.0
        audiobook_request.processing_status = "download_initiated"
        session.add(audiobook_request)
        session.commit()

        # Notifications will be handled by the caller
        return True
    else:
        logger.error("Failed to add torrent to qBittorrent directly")
        # Notifications will be handled by the caller
        return False


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
    book: Audiobook,
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
