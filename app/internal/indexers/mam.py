from dataclasses import dataclass
import json
from typing import override
from urllib.parse import urlencode, urljoin

from pydantic import BaseModel

from app.internal.indexers.abstract import (
    AbstractIndexer,
    SessionContainer,
)
from app.internal.indexers.configuration import (
    Configurations,
    IndexerConfiguration,
    ValuedConfigurations,
)
from app.internal.models import Audiobook, ProwlarrSource
from app.util.log import logger


class MamConfigurations(Configurations):
    mam_session_id: IndexerConfiguration[str] = IndexerConfiguration(
        type_=str,
        display_name="MAM Session ID",
        required=True,
    )


@dataclass
class ValuedMamConfigurations(ValuedConfigurations):
    mam_session_id: str


class _Result(BaseModel):
    id: int
    author_info: str | None = None
    narrator_info: str | None = None
    personal_freeleech: int
    free: int
    fl_vip: int
    vip: int
    filetype: str

    @property
    def authors(self) -> list[str]:
        """Response type of authors and narrators is a stringified json object"""

        if not self.author_info:
            return []
        content = json.loads(self.author_info)  # pyright: ignore[reportAny]
        if isinstance(content, dict):
            return list(x for x in content.values() if isinstance(x, str))  # pyright: ignore[reportUnknownVariableType]
        return []

    @property
    def narrators(self) -> list[str]:
        if not self.narrator_info:
            return []
        content = json.loads(self.narrator_info)  # pyright: ignore[reportAny]
        if isinstance(content, dict):
            return list(x for x in content.values() if isinstance(x, str))  # pyright: ignore[reportUnknownVariableType]
        return []


class _MamResponse(BaseModel):
    data: list[_Result]


class MamIndexer(AbstractIndexer[MamConfigurations]):
    name: str = "MyAnonamouse"
    results: dict[int, _Result] = dict()

    @override
    @staticmethod
    async def get_configurations(
        container: SessionContainer,
    ) -> MamConfigurations:
        return MamConfigurations()

    @override
    async def setup(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        book: Audiobook,
        container: SessionContainer,
        configurations: ValuedMamConfigurations,
    ):
        if not await self.is_enabled(container, configurations):
            return

        params = {
            "tor[text]": book.title,
            "tor[main_cat]": [13],  # MAM audiobook category
            "tor[searchIn]": "torrents",
            "tor[srchIn][author]": "true",
            "tor[srchIn][title]": "true",
            "tor[searchType]": "active",  # only search for torrents with at least 1 seeder.
            "startNumber": 0,
            "perpage": 100,
        }

        url = urljoin(
            "https://www.myanonamouse.net",
            f"/tor/js/loadSearchJSONbasic.php?{urlencode(params, doseq=True)}",
        )

        session_id = configurations.mam_session_id

        try:
            async with container.client_session.get(
                url, cookies={"mam_id": session_id}
            ) as response:
                if response.status == 403:
                    logger.error(
                        "Mam: Failed to authenticate", response=await response.text()
                    )
                    return
                if not response.ok:
                    logger.error("Mam: Failed to query", response=await response.text())
                    return
                json_body = await response.json()  # pyright: ignore[reportAny]
                if "error" in json_body:
                    logger.error("Mam: Error in response", error=json_body["error"])
                    return
                search_results = _MamResponse.model_validate(json_body)
        except Exception as e:
            logger.error("Mam: Exception during search", exception=e)
            return

        for result in search_results.data:
            self.results[result.id] = result
        logger.info("Mam: Retrieved results", results_amount=len(self.results))

    @override
    async def is_matching_source(
        self,
        source: ProwlarrSource,
        container: SessionContainer,
    ):
        return source.info_url is not None and source.info_url.startswith(
            "https://www.myanonamouse.net/t/"
        )

    @override
    async def edit_source_metadata(
        self,
        source: ProwlarrSource,
        container: SessionContainer,
    ):
        mam_id = source.guid.split("/")[-1]
        if not mam_id.isdigit():
            return
        mam_id_int = int(mam_id)
        result = self.results.get(mam_id_int)
        if result is None:
            return

        source.book_metadata.authors = result.authors
        source.book_metadata.narrators = result.narrators

        indexer_flags: set[str] = set(source.indexer_flags)
        if result.personal_freeleech == 1:
            indexer_flags.add("personal_freeleech")
            indexer_flags.add("freeleech")
        if result.free == 1:
            indexer_flags.add("free")
            indexer_flags.add("freeleech")
        if result.fl_vip == 1:
            indexer_flags.add("fl_vip")
            indexer_flags.add("freeleech")
        if result.vip == 1:
            indexer_flags.add("vip")

        source.indexer_flags = list(indexer_flags)

        source.book_metadata.filetype = result.filetype
