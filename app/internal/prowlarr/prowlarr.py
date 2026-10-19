import html
import json
import posixpath
import time
import uuid
from datetime import datetime
from typing import Literal, cast
from urllib.parse import parse_qs, urlencode, urlparse

from aiohttp import ClientResponse, ClientSession, NonHttpUrlRedirectClientError
from pydantic import BaseModel, TypeAdapter
from sqlmodel import Session, select
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
)
from app.internal.notifications import (
    send_all_manual_notifications,
    send_all_notifications,
)
from app.internal.prowlarr.source_metadata import edit_source_metadata
from app.internal.prowlarr.util import (
    prowlarr_config,
    prowlarr_indexer_cache,
    prowlarr_source_cache,
)
from app.util.connection import USER_AGENT
from app.util.log import logger


class DownloadFailed(Exception):
    status: int
    message: str

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def _info_hash_from_magnet(magnet_url: str) -> str | None:
    query = parse_qs(urlparse(magnet_url).query)
    prefix = "urn:btih:"
    for xt in query.get("xt", []):
        if xt.lower().startswith(prefix):
            return xt[len(prefix) :]
    return None


async def _get_torrent_info_hash(
    client_session: ClientSession, download_url: str
) -> str | None:
    logger.debug("Fetching torrent info hash", download_url=download_url)
    try:
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
    except NonHttpUrlRedirectClientError as e:
        # Some indexers redirect the torrent URL to a magnet URI.
        location = str(cast(object, e.args[0])) if e.args else ""
        logger.debug(
            "Torrent download redirected",
            download_url=download_url,
            location=location,
        )
        return _info_hash_from_magnet(location)
    except Exception as e:
        logger.error("Failed to fetch torrent", download_url=download_url, error=str(e))
    return None


async def start_download(
    *,
    session: Session,
    client_session: ClientSession,
    guid: str,
    indexer_id: int,
    prowlarr_source: ProwlarrSource | None = None,
    asin_or_uuid: str | None = None,
) -> ClientResponse:
    prowlarr_config.raise_if_invalid(session)
    base_url = prowlarr_config.get_base_url(session)
    api_key = prowlarr_config.get_api_key(session)
    assert base_url is not None and api_key is not None

    url = posixpath.join(base_url, "api/v1/search")
    logger.debug("Starting download", guid=guid)
    headers = {"X-Api-Key": api_key, "User-Agent": USER_AGENT}

    manual_book_request: ManualBookRequest | None = None
    try:
        uuid_obj = uuid.UUID(asin_or_uuid)
        manual_book_request = session.get(ManualBookRequest, uuid_obj)
    except ValueError:
        pass

    async with client_session.post(
        url,
        json={"guid": guid, "indexerId": indexer_id},
        headers=headers,
    ) as response:
        if not response.ok:
            body = await response.text()
            message = response.reason or "<unknown>"
            try:
                parsed = cast(object, json.loads(body))
                if isinstance(parsed, dict):
                    raw_message = cast(dict[str, object], parsed).get("message")
                    if isinstance(raw_message, str) and raw_message.strip():
                        message = raw_message.strip()
            except ValueError:
                if body.strip():
                    message = body.strip()

            logger.error(
                "Failed to start download",
                guid=guid,
                response=response,
                message=message,
            )

            replacements = {
                "errorStatus": str(response.status),
                "errorReason": message,
            }
            try:
                if manual_book_request:
                    await send_all_manual_notifications(
                        EventEnum.on_failed_download,
                        manual_book_request,
                        replacements,
                    )
                else:
                    await send_all_notifications(
                        EventEnum.on_failed_download,
                        asin_or_uuid,
                        replacements,
                    )
            except Exception as e:
                logger.error(
                    "Failed to send download failure notification",
                    guid=guid,
                    error=str(e),
                )
            raise DownloadFailed(response.status, message)

        # Find additional metadata/replacements to pass along notifications
        additional_replacements: dict[str, str] = {}
        if (
            prowlarr_source
            and prowlarr_source.download_url
            and prowlarr_source.protocol == "torrent"
            and (
                info_hash := await _get_torrent_info_hash(
                    client_session, prowlarr_source.download_url
                )
            )
        ) or (
            prowlarr_source
            and prowlarr_source.magnet_url
            and prowlarr_source.protocol == "torrent"
            and (info_hash := _info_hash_from_magnet(prowlarr_source.magnet_url))
        ):
            additional_replacements["torrentInfoHash"] = info_hash

        if prowlarr_source:
            additional_replacements["sourceSizeMB"] = str(prowlarr_source.size_MB)
            additional_replacements["sourceTitle"] = prowlarr_source.title
            additional_replacements["indexerName"] = prowlarr_source.indexer
            additional_replacements["sourceProtocol"] = prowlarr_source.protocol

        logger.debug("Download successfully started", guid=guid)
        if manual_book_request:
            manual_book_request.downloaded = True
            session.add(manual_book_request)
            session.commit()
            await send_all_manual_notifications(
                EventEnum.on_successful_download,
                manual_book_request,
                additional_replacements,
            )
        else:
            same_books = session.exec(
                select(Audiobook).where(Audiobook.asin == asin_or_uuid)
            ).all()
            for b in same_books:
                b.downloaded = True
                session.add(b)
            session.commit()

            await send_all_notifications(
                EventEnum.on_successful_download,
                asin_or_uuid,
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
