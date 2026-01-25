import json
from typing import Literal

from sqlmodel import Session

from app.internal.models import Indexer, ProwlarrSource
from app.util.cache import SimpleCache, StringConfigCache
from app.util.log import logger


class ProwlarrMisconfigured(ValueError):
    pass


ProwlarrConfigKey = Literal[
    "prowlarr_api_key",
    "prowlarr_base_url",
    "prowlarr_source_ttl",
    "prowlarr_categories",
    "prowlarr_indexers",
    "prowlarr_default_language",
]


class ProwlarrConfig(StringConfigCache[ProwlarrConfigKey]):
    def raise_if_invalid(self, session: Session):
        if not self.get_base_url(session):
            raise ProwlarrMisconfigured("Prowlarr base url not set")
        if not self.get_api_key(session):
            raise ProwlarrMisconfigured("Prowlarr base url not set")

    def is_valid(self, session: Session) -> bool:
        return (
            self.get_base_url(session) is not None
            and self.get_api_key(session) is not None
        )

    def get_api_key(self, session: Session) -> str | None:
        return self.get(session, "prowlarr_api_key")

    def set_api_key(self, session: Session, api_key: str):
        self.set(session, "prowlarr_api_key", api_key)

    def get_base_url(self, session: Session) -> str | None:
        path = self.get(session, "prowlarr_base_url")
        if path:
            return path.rstrip("/")
        return None

    def set_base_url(self, session: Session, base_url: str):
        self.set(session, "prowlarr_base_url", base_url)

    def get_source_ttl(self, session: Session) -> int:
        return self.get_int(session, "prowlarr_source_ttl", 24 * 60 * 60)

    def set_source_ttl(self, session: Session, source_ttl: int):
        self.set_int(session, "prowlarr_source_ttl", source_ttl)

    def get_categories(self, session: Session) -> list[int]:
        categories = self.get(session, "prowlarr_categories")
        if categories is None:
            return [3030]
        return json.loads(categories)  # pyright: ignore[reportAny]

    def set_categories(self, session: Session, categories: list[int]):
        self.set(session, "prowlarr_categories", json.dumps(categories))

    def get_indexers(self, session: Session) -> list[int]:
        indexers = self.get(session, "prowlarr_indexers")
        if indexers is None:
            return []
        return json.loads(indexers)  # pyright: ignore[reportAny]

    def set_indexers(self, session: Session, indexers: list[int]):
        self.set(session, "prowlarr_indexers", json.dumps(indexers))

    def get_default_language(self, session: Session) -> str:
        return self.get(session, "prowlarr_default_language", "us")

    def set_default_language(self, session: Session, language: str):
        self.set(session, "prowlarr_default_language", language)


prowlarr_config = ProwlarrConfig()
prowlarr_source_cache = SimpleCache[list[ProwlarrSource], str]()
prowlarr_indexer_cache = SimpleCache[Indexer, str]()


def flush_prowlarr_cache():
    logger.info("Flushing prowlarr caches")
    prowlarr_source_cache.flush()
    prowlarr_indexer_cache.flush()
