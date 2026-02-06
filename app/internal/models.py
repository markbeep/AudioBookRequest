import html
import json
import uuid
from datetime import datetime
from enum import Enum
from typing import Annotated, Literal, Union, cast

from pydantic import BaseModel, ConfigDict
from sqlmodel import JSON, Column, DateTime, Field, SQLModel, func
from sqlmodel._compat import SQLModelConfig
from sqlmodel.main import Relationship


class BaseSQLModel(SQLModel):
    pass


class GroupEnum(str, Enum):
    untrusted = "untrusted"
    trusted = "trusted"
    admin = "admin"


class User(BaseSQLModel, table=True):
    username: str = Field(primary_key=True)
    password: str
    group: GroupEnum = Field(
        default=GroupEnum.untrusted,
        sa_column_kwargs={"server_default": "untrusted"},
    )
    root: bool = False
    extra_data: str | None = None

    # TODO: Add last_login
    # last_login: datetime = Field(
    #     default_factory=datetime.now, sa_column_kwargs={"server_default": "now()"}
    # )

    """
    untrusted: Requests need to be manually reviewed
    trusted: Requests are automatically downloaded if possible
    admin: Can approve or deny requests, change settings, etc.
    """

    def is_above(self, group: GroupEnum) -> bool:
        if group == "admin":
            if self.group != GroupEnum.admin:
                return False
        elif group == "trusted":
            if self.group not in [GroupEnum.admin, GroupEnum.trusted]:
                return False
        return True

    def can_download(self):
        return self.is_above(GroupEnum.trusted)

    def is_admin(self):
        return self.group == GroupEnum.admin

    def is_self(self, username: str):
        # To prevent '==' in Jinja2, since that breaks formatting
        return self.username == username


class Audiobook(BaseSQLModel, table=True):
    """A cached Audible audiobook result. Used for both the search results and also linked to via a foreign key for requests."""

    asin: str = Field(primary_key=True)
    title: str
    subtitle: str | None
    authors: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    narrators: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    cover_image: str | None
    release_date: datetime
    runtime_length_min: int
    updated_at: datetime = Field(
        default_factory=datetime.now,
        sa_column=Column(
            onupdate=func.now(),
            server_default=func.now(),
            type_=DateTime,
            nullable=False,
        ),
    )
    downloaded: bool = False

    requests: list["AudiobookRequest"] = Relationship(back_populates="audiobook")  # pyright: ignore[reportAny]

    model_config: SQLModelConfig = cast(
        SQLModelConfig, cast(object, ConfigDict(arbitrary_types_allowed=True))
    )

    @property
    def runtime_length_hrs(self):
        return round(self.runtime_length_min / 60, 1)


class AudiobookWithRequests(BaseModel):
    book: Audiobook
    requests: list[AudiobookRequest]
    username: str | None

    @property
    def already_requested(self):
        if self.username:
            return any(req.user_username == self.username for req in self.requests)
        return len(self.requests) > 0


class AudiobookRequest(BaseSQLModel, table=True):
    asin: str = Field(
        primary_key=True,
        foreign_key="audiobook.asin",
        ondelete="CASCADE",
    )
    user_username: str = Field(
        primary_key=True,
        foreign_key="user.username",
        ondelete="CASCADE",
    )
    updated_at: datetime = Field(
        default_factory=datetime.now,
        sa_column=Column(
            onupdate=func.now(),
            server_default=func.now(),
            type_=DateTime,
            nullable=False,
        ),
    )

    audiobook: Audiobook = Relationship(back_populates="requests")  # pyright: ignore[reportAny]

    model_config: SQLModelConfig = cast(
        SQLModelConfig, cast(object, ConfigDict(arbitrary_types_allowed=True))
    )


class AudiobookWishlistResult(BaseModel):
    book: Audiobook
    requests: list[AudiobookRequest]
    download_error: str | None = None

    @property
    def amount_requested(self):
        return len(self.requests)

    @property
    def requested_by_usernames(self):
        return "\n".join(req.user_username for req in self.requests)


class ManualBookRequest(BaseSQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_username: str = Field(foreign_key="user.username", ondelete="CASCADE")
    title: str
    subtitle: str | None = None
    authors: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    narrators: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    publish_date: str | None = None
    additional_info: str | None = None
    updated_at: datetime = Field(
        default_factory=datetime.now,
        sa_column=Column(
            onupdate=func.now(),
            server_default=func.now(),
            type_=DateTime,
            nullable=False,
        ),
    )
    downloaded: bool = False

    model_config: SQLModelConfig = cast(
        SQLModelConfig, cast(object, ConfigDict(arbitrary_types_allowed=True))
    )


class BookMetadata(BaseSQLModel):
    """extra metadata that can be added to sources to better rank them"""

    title: str | None = None
    subtitle: str | None = None
    authors: list[str] = []
    narrators: list[str] = []
    filetype: str | None = None


class BaseSource(BaseSQLModel):
    guid: str
    indexer_id: int
    indexer: str
    title: str
    size: int  # in bytes
    publish_date: datetime
    info_url: str | None
    indexer_flags: list[str]
    download_url: str | None = None
    magnet_url: str | None = None

    book_metadata: BookMetadata = BookMetadata()

    @property
    def size_MB(self):
        return round(self.size / 1e6, 1)


class TorrentSource(BaseSource):
    protocol: Literal["torrent"] = "torrent"
    seeders: int
    leechers: int


class UsenetSource(BaseSource):
    protocol: Literal["usenet"] = "usenet"
    grabs: int


ProwlarrSource = Annotated[
    Union[TorrentSource, UsenetSource], Field(discriminator="protocol")
]


class Indexer(BaseModel, frozen=True):
    id: int
    name: str
    enable: bool
    privacy: str


class Config(BaseSQLModel, table=True):
    key: str = Field(primary_key=True)
    value: str


class EventEnum(str, Enum):
    on_new_request = "onNewRequest"
    on_successful_download = "onSuccessfulDownload"
    on_failed_download = "onFailedDownload"


class NotificationBodyTypeEnum(str, Enum):
    text = "text"
    json = "json"


class Notification(BaseSQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str
    url: str
    headers: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))
    event: EventEnum
    body_type: NotificationBodyTypeEnum
    body: str
    enabled: bool

    @property
    def serialized_headers(self):
        return html.escape(json.dumps(self.headers))


class APIKeyResponse(BaseModel):
    id: uuid.UUID
    name: str
    enabled: bool


class APIKey(BaseSQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_username: str = Field(foreign_key="user.username", ondelete="CASCADE")
    name: str
    key_hash: str
    created_at: datetime = Field(
        default_factory=datetime.now,
        sa_column=Column(
            server_default=func.now(),
            type_=DateTime,
            nullable=False,
        ),
    )
    last_used: datetime | None = Field(
        default=None,
        sa_column=Column(
            type_=DateTime,
            nullable=True,
        ),
    )
    enabled: bool = True
