import re
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
)
from app.internal.indexers.mam_models import _Result, _MamResponse
from app.internal.models import Audiobook, ProwlarrSource
from app.util.log import logger

# Mimic browser headers to avoid detection
MAM_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
MAM_HEADERS = {
    "User-Agent": MAM_USER_AGENT,
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.myanonamouse.net/tor/browse.php",
    "X-Requested-With": "XMLHttpRequest",
}

async def fetch_mam_book_details(
    container: SessionContainer,
    configurations: "ValuedMamConfigurations",
    mam_id: int,
) -> _Result | None:
    """
    Get detailed metadata for a specific book from MAM.
    """
    params = {
        "tor[id]": mam_id,
        "tor[main_cat]": [13],
    }

    url = urljoin(
        "https://www.myanonamouse.net",
        f"/tor/js/loadSearchJSONbasic.php?{urlencode(params, doseq=True)}",
    )

    session_id = configurations.mam_session_id
    if session_id.startswith("mam_id="):
        session_id = session_id[7:]

    logger.info("Mam: Fetching book details", mam_id=mam_id)
    try:
        async with container.client_session.get(
            url, cookies={"mam_id": session_id}, headers=MAM_HEADERS
        ) as response:
            if response.status == 403:
                logger.error("Mam: Auth failed (403). Check session ID.", mam_id=mam_id)
                return None
            
            if not response.ok:
                logger.error("Mam: Request failed", status=response.status, mam_id=mam_id)
                return None

            try:
                json_body = await response.json()
            except Exception as e:
                text = await response.text()
                logger.error("Mam: Parse error", error=str(e), sample=text[:100])
                return None

            if "error" in json_body:
                logger.error("Mam: API error", error=json_body["error"], mam_id=mam_id)
                return None

            search_results = _MamResponse.model_validate(json_body)
            if search_results.data:
                result = search_results.data[0]
                logger.info("Mam: Found book info", title=result.display_title, mam_id=mam_id)

                # Try to get the synopsis image from the book page
                try:
                    book_page_url = f"https://www.myanonamouse.net/t/{mam_id}"
                    async with container.client_session.get(
                        book_page_url, cookies={"mam_id": session_id}, headers=MAM_HEADERS
                    ) as page_response:
                        if page_response.ok:
                            html_content = await page_response.text()
                            match = re.search(
                                r'<div id="synopsis".*?<img src="(.*?)"',
                                html_content,
                                re.DOTALL,
                            )
                            if match:
                                result.synopsis_image = match.group(1)
                except Exception as e:
                    logger.debug("Mam: Failed to scrape image", error=str(e))

                return result
            else:
                logger.warning("Mam: Book not found", mam_id=mam_id)
                return None
    except Exception as e:
        logger.error("Mam: Fetch error", error=str(e), mam_id=mam_id)
        return None


class MamConfigurations(Configurations):
    mam_session_id: IndexerConfiguration[str] = IndexerConfiguration(
        type_=str,
        display_name="MAM Session ID",
        required=True,
    )


class ValuedMamConfigurations(BaseModel):
    mam_session_id: str


class MamIndexer(AbstractIndexer[MamConfigurations]):
    name: str = "MyAnonamouse"

    def __init__(self):
        self.results: dict[int, _Result] = {}

    @override
    @staticmethod
    async def get_configurations(
        container: SessionContainer,
    ) -> MamConfigurations:
        return MamConfigurations()

    @override
    async def setup(
        self,
        book: Audiobook,
        container: SessionContainer,
        configurations: ValuedMamConfigurations,
    ):
        if not await self.is_enabled(container, configurations):
            return

        params = {
            "tor[text]": book.title,
            "tor[main_cat]": [13, 14], # 13: Audiobooks, 14: Radio/Audio Drama
            "tor[searchIn]": "torrents",
            "tor[srchIn][author]": "true",
            "tor[srchIn][title]": "true",
            "tor[searchType]": "active",
            "startNumber": 0,
            "perpage": 100,
        }

        url = urljoin(
            "https://www.myanonamouse.net",
            f"/tor/js/loadSearchJSONbasic.php?{urlencode(params, doseq=True)}",
        )

        session_id = configurations.mam_session_id
        if session_id.startswith("mam_id="):
            session_id = session_id[7:]

        try:
            logger.info("Mam: Searching for book", title=book.title)
            async with container.client_session.get(
                url, 
                cookies={"mam_id": session_id}, 
                headers=MAM_HEADERS
            ) as response:
                if response.status == 403:
                    logger.error("Mam: Search auth failed (403)")
                    return
                if not response.ok:
                    logger.error("Mam: Search failed", status=response.status)
                    return
                
                try:
                    json_body = await response.json()
                except Exception as e:
                    logger.error("Mam: Search parse error", error=str(e))
                    return
                
                if "error" in json_body:
                    logger.error("Mam: Search API error", error=json_body["error"])
                    return
                
                search_results = _MamResponse.model_validate(json_body)
                logger.info("Mam: Found results", count=len(search_results.data))
        except Exception as e:
            logger.error("Mam: Search exception", error=str(e))
            return

        for result in search_results.data:
            self.results[result.id] = result

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
        from app.internal.metadata import generate_opf_for_mam
        mam_id = source.guid.split("/")[-1]
        if not mam_id.isdigit():
            return
        
        mam_id_int = int(mam_id)
        result = self.results.get(mam_id_int)
        if result is None:
            return

        source.book_metadata.authors = result.authors
        source.book_metadata.narrators = result.narrators

        flags: set[str] = set(source.indexer_flags)
        if result.personal_freeleech == 1:
            flags.update(["personal_freeleech", "freeleech"])
        if result.free == 1:
            flags.update(["free", "freeleech"])
        if result.fl_vip == 1:
            flags.update(["fl_vip", "freeleech"])
        if result.vip == 1:
            flags.add("vip")

        source.indexer_flags = list(flags)
        source.book_metadata.filetype = result.filetype
        source.book_metadata.metadata_file_content = generate_opf_for_mam(result)
