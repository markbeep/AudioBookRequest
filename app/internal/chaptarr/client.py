import posixpath
from typing import ClassVar

from aiohttp import ClientResponse, ClientSession
from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError
from sqlmodel import Session

from app.internal.chaptarr.config import chaptarr_config
from app.internal.models import Audiobook, EventEnum
from app.internal.notifications import send_all_notifications
from app.util.connection import USER_AGENT
from app.util.log import logger


class ChaptarrError(Exception):
    message: str
    status: int | None

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


class _ChaptarrModel(BaseModel):
    # lookup results are echoed back on add, so unknown fields must survive.
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")


class ChaptarrAuthor(_ChaptarrModel):
    id: int = 0
    foreignAuthorId: str | None = None
    authorName: str | None = None
    monitored: bool = False
    audiobookMonitored: bool | None = None
    audiobookRootFolderPath: str | None = None
    audiobookQualityProfileId: int | None = None
    audiobookMetadataProfileId: int | None = None


class ChaptarrBook(_ChaptarrModel):
    id: int = 0
    title: str | None = None
    foreignBookId: str | None = None
    foreignEditionId: str | None = None
    asin: str | None = None
    audibleASIN: str | None = None
    mediaType: str | None = None
    monitored: bool = False
    audiobookMonitored: bool | None = None
    author: ChaptarrAuthor | None = None
    addOptions: dict[str, object] | None = None


class ChaptarrRootFolder(_ChaptarrModel):
    path: str
    isEffectiveDefaultAudiobook: bool = False
    audiobookQualityProfileId: int | None = None
    audiobookMetadataProfileId: int | None = None


class _ChaptarrProfile(BaseModel):
    id: int


_Lookup = TypeAdapter(list[ChaptarrBook])
_RootFolders = TypeAdapter(list[ChaptarrRootFolder])
_Profiles = TypeAdapter(list[_ChaptarrProfile])


def _headers(session: Session) -> dict[str, str]:
    api_key = chaptarr_config.get_api_key(session)
    assert api_key is not None
    return {"X-Api-Key": api_key, "User-Agent": USER_AGENT}


def _base_url(session: Session) -> str:
    base_url = chaptarr_config.get_base_url(session)
    assert base_url is not None
    return base_url


async def _error_message(response: ClientResponse, status: int) -> str:
    body = await response.text()
    if body.strip():
        return f"{status}: {body.strip()[:300]}"
    return f"status {status}"


async def chaptarr_connected(session: Session, client_session: ClientSession) -> bool:
    if not chaptarr_config.is_valid(session):
        return False
    url = posixpath.join(_base_url(session), "api/v1/system/status")
    try:
        async with client_session.get(url, headers=_headers(session)) as response:
            return response.ok
    except Exception as e:
        logger.debug("Chaptarr: status check failed", error=str(e))
        return False


async def _get_root_folder(
    session: Session, client_session: ClientSession
) -> ChaptarrRootFolder:
    url = posixpath.join(_base_url(session), "api/v1/rootfolder")
    async with client_session.get(
        url,
        headers=_headers(session),
        params={"mediaType": "audiobook"},
    ) as response:
        if not response.ok:
            raise ChaptarrError(
                await _error_message(response, response.status), response.status
            )
        folders = _RootFolders.validate_python(await response.json())

    if not folders:
        raise ChaptarrError(
            "Chaptarr has no audiobook root folder; add one in Chaptarr first"
        )
    for folder in folders:
        if folder.isEffectiveDefaultAudiobook:
            return folder
    return folders[0]


async def _first_profile_id(
    session: Session, client_session: ClientSession, path: str
) -> int | None:
    url = posixpath.join(_base_url(session), f"api/v1/{path}")
    async with client_session.get(url, headers=_headers(session)) as response:
        if not response.ok:
            raise ChaptarrError(
                await _error_message(response, response.status), response.status
            )
        profiles = _Profiles.validate_python(await response.json())
    return profiles[0].id if profiles else None


async def _lookup_book(
    session: Session, client_session: ClientSession, asin: str
) -> ChaptarrBook:
    url = posixpath.join(_base_url(session), "api/v1/book/lookup")
    async with client_session.get(
        url,
        headers=_headers(session),
        params={"term": f"az:{asin}", "mediaType": "audiobook"},
    ) as response:
        if response.status == 202:
            raise ChaptarrError(
                "Chaptarr is still resolving this book, try again later", 202
            )
        if not response.ok:
            raise ChaptarrError(
                await _error_message(response, response.status), response.status
            )
        try:
            books = _Lookup.validate_python(await response.json())
        except ValidationError as e:
            raise ChaptarrError(f"Unexpected Chaptarr lookup response: {e}") from e

    if not books:
        raise ChaptarrError(f"Chaptarr has no match for ASIN {asin}")

    for book in books:
        if asin.upper() in {
            candidate.upper()
            for candidate in (book.asin, book.audibleASIN)
            if candidate
        }:
            return book
    return books[0]


async def _add_book_by_asin(
    session: Session, client_session: ClientSession, asin: str
) -> None:
    root_folder = await _get_root_folder(session, client_session)

    quality_profile_id = (
        root_folder.audiobookQualityProfileId
        or await _first_profile_id(session, client_session, "qualityprofile")
    )
    if quality_profile_id is None:
        raise ChaptarrError("Chaptarr has no quality profile configured")

    metadata_profile_id = root_folder.audiobookMetadataProfileId or (
        await _first_profile_id(session, client_session, "metadataprofile")
    )

    book = await _lookup_book(session, client_session, asin)
    author = book.author or ChaptarrAuthor()
    author.monitored = True
    author.audiobookMonitored = True
    author.audiobookRootFolderPath = root_folder.path
    author.audiobookQualityProfileId = quality_profile_id
    author.audiobookMetadataProfileId = metadata_profile_id

    book.author = author
    book.mediaType = "audiobook"
    book.monitored = True
    book.audiobookMonitored = True
    book.addOptions = {**(book.addOptions or {}), "searchForNewBook": True}

    url = posixpath.join(_base_url(session), "api/v1/book")
    async with client_session.post(
        url,
        headers=_headers(session),
        params={"mediaType": "audiobook"},
        json=book.model_dump(mode="json", exclude_none=True),
    ) as response:
        if response.ok or response.status == 202:
            logger.info("Chaptarr: book added", asin=asin, status=response.status)
            return
        raise ChaptarrError(
            await _error_message(response, response.status), response.status
        )


async def start_chaptarr_download(
    session: Session, client_session: ClientSession, book: Audiobook
) -> None:
    """Hand a book request to Chaptarr, which handles search, download and import."""
    try:
        await _add_book_by_asin(session, client_session, book.asin)
    except Exception as exc:
        # Transport errors, bad JSON and response validation all need to reach
        # the failure notification too, not just intentional ChaptarrErrors.
        e = exc if isinstance(exc, ChaptarrError) else ChaptarrError(str(exc))
        logger.error("Chaptarr: failed to add book", asin=book.asin, error=e.message)
        try:
            await send_all_notifications(
                EventEnum.on_failed_download,
                book.asin,
                {
                    "errorStatus": str(e.status) if e.status else "chaptarr",
                    "errorReason": e.message,
                },
            )
        except Exception:
            logger.error("Chaptarr: failed to send download failure notification")
        raise e from exc

    book.downloaded = True
    session.add(book)
    session.commit()
    await send_all_notifications(
        EventEnum.on_successful_download,
        book.asin,
        {"indexerName": "Chaptarr"},
    )
