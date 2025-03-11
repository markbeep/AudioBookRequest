import json
import logging
from datetime import datetime
from typing import Any, Literal, Optional
from urllib.parse import urlencode, urljoin

from aiohttp import ClientSession
from sqlmodel import Session

from app.internal.models import (
    TorrentSource,
    ProwlarrSource,
)
from app.util.cache import SimpleCache, StringConfigCache

logger = logging.getLogger(__name__)


class MamMisconfigured(ValueError):
    pass


MamConfigKey = Literal["mam_session_id", "mam_source_ttl", "mam_active"]


class MamConfig(StringConfigCache[MamConfigKey]):
    def raise_if_invalid(self, session: Session):
        if not self.get_session_id(session):
            raise MamMisconfigured("mam_id not set")

    def is_valid(self, session: Session) -> bool:
        return (
            self.get_session_id(session) is not None
            and self.get_session_id(session) != ""
        )

    def get_session_id(self, session: Session) -> Optional[str]:
        return self.get(session, "mam_session_id")

    def set_mam_id(self, session: Session, mam_id: str):
        self.set(session, "mam_session_id", mam_id)

    def get_source_ttl(self, session: Session) -> int:
        return self.get_int(session, "mam_source_ttl", 24 * 60 * 60)

    def set_source_ttl(self, session: Session, source_ttl: int):
        self.set_int(session, "mam_source_ttl", source_ttl)

    def is_active(self, session: Session) -> bool:
        return self.get(session, "mam_active") == "True"

    def set_active(self, session: Session, state: bool):
        self.set(session, "mam_active", str(state))


mam_config = MamConfig()
mam_source_cache = SimpleCache[dict[str, TorrentSource]]()


def flush_Mam_cache():
    mam_source_cache.flush()


# Downloading is still handled via prowlarr.


async def query_mam(
    session: Session,
    client_session: ClientSession,
    query: Optional[str],
    force_refresh: bool = False,
) -> dict[str, TorrentSource]:
    if not query:
        return dict()

    session_id = mam_config.get_session_id(session)
    assert session_id is not None

    if not force_refresh:
        source_ttl = mam_config.get_source_ttl(session)
        cached_sources = mam_source_cache.get(source_ttl, "mam_" + query)
        if cached_sources:
            return cached_sources
    params: dict[str, Any] = {
        "tor[text]": query,  # book title + author(s)
        "tor[main_cat]": [13],  # MAM audiobook category
        "tor[searchIn]": "torrents",
        "tor[srchIn][author]": "true",
        "tor[srchIn][title]": "true",
        "tor[searchType]": "active",  # only search for torrents with at least 1 seeder.
        "startNumber": 0,
        "perpage": 100,
    }

    base_url = "https://www.myanonamouse.net"
    url = urljoin(
        base_url, f"/tor/js/loadSearchJSONbasic.php?{urlencode(params, doseq=True)}"
    )

    logger.info("Querying Mam: %s", url)

    async with client_session.get(url, cookies={"mam_id": session_id}) as response:
        search_results = await response.json()
    # Storing in dict for faster retrieval by guid
    sources: dict[str, TorrentSource] = dict()

    for result in search_results["data"]:
        # TODO reduce to just authors / narrator unless there is a use for the other data.
        sources.update(
            {
                f'https://www.myanonamouse.net/t/{result["id"]}': TorrentSource(
                    protocol="torrent",
                    guid=f'https://www.myanonamouse.net/t/{result["id"]}',
                    indexer_id=-1,  # We don't know MAM's id within prowlarr.
                    indexer="MyAnonamouse",
                    title=result["title"],
                    seeders=result.get("seeders", 0),
                    leechers=result.get("leechers", 0),
                    size=-1,
                    info_url=f'https://www.myanonamouse.net/t/{result["id"]}',
                    indexer_flags=(
                        ["freeleech"] if result["personal_freeleech"] == 1 else []
                    ),  # TODO add differentiate between freeleech and VIP freeleech availible flags in result: [free, fl_vip, personal_freeleech]
                    publish_date=datetime.fromisoformat(result["added"]),
                    authors=(
                        list(json.loads(result["author_info"]).values())
                        if result["author_info"]
                        else []
                    ),
                    narrators=(
                        list(json.loads(result["narrator_info"]).values())
                        if result["narrator_info"]
                        else []
                    ),
                )
            }
        )

    mam_source_cache.set(sources, "mam_" + query)

    return sources


def inject_mam_metadata(
    prowlarrData: list[ProwlarrSource], mamData: dict[str, TorrentSource]
) -> list[ProwlarrSource]:
    for p in prowlarrData:
        m = mamData.get(p.guid)
        if m is None:
            continue
        p.authors = m.authors
        p.narrators = m.narrators

    return prowlarrData
