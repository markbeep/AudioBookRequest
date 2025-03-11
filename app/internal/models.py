# pyright: reportUnknownVariableType=false
import uuid
from datetime import datetime
from enum import Enum
from typing import Annotated, Literal, Optional, Union

from sqlmodel import JSON, Column, DateTime, Field, SQLModel, UniqueConstraint, func


class BaseModel(SQLModel):
    pass


class GroupEnum(str, Enum):
    untrusted = "untrusted"
    trusted = "trusted"
    admin = "admin"


class User(BaseModel, table=True):
    username: str = Field(primary_key=True)
    password: str
    group: GroupEnum = Field(
        default=GroupEnum.untrusted,
        sa_column_kwargs={"server_default": "untrusted"},
    )
    root: bool = False
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


class BaseBook(BaseModel):
    asin: str
    title: str
    subtitle: Optional[str]
    authors: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    narrators: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    cover_image: Optional[str]
    release_date: datetime
    runtime_length_min: int
    downloaded: bool = False

    @property
    def runtime_length_hrs(self):
        return round(self.runtime_length_min / 60, 1)


class BookSearchResult(BaseBook):
    already_requested: bool = False


class BookWishlistResult(BaseBook):
    amount_requested: int = 0
    download_error: Optional[str] = None


class BookRequest(BaseBook, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_username: Optional[str] = Field(
        default=None, foreign_key="user.username", ondelete="CASCADE"
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

    __table_args__ = (
        UniqueConstraint("asin", "user_username", name="unique_asin_user"),
    )

    class Config:  # pyright: ignore[reportIncompatibleVariableOverride]
        arbitrary_types_allowed = True


class ManualBookRequest(BaseModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_username: str = Field(foreign_key="user.username", ondelete="CASCADE")
    title: str
    subtitle: Optional[str] = None
    authors: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    narrators: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    publish_date: Optional[str] = None
    additional_info: Optional[str] = None
    updated_at: datetime = Field(
        default_factory=datetime.now,
        sa_column=Column(
            onupdate=func.now(),
            server_default=func.now(),
            type_=DateTime,
            nullable=False,
        ),
    )

    class Config:  # pyright: ignore[reportIncompatibleVariableOverride]
        arbitrary_types_allowed = True


class BaseSource(BaseModel):
    guid: str
    indexer_id: int
    indexer: str
    title: str
    authors: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    narrators: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    size: int  # in bytes
    publish_date: datetime
    info_url: str
    indexer_flags: list[str]
    download_url: Optional[str] = None
    magnet_url: Optional[str] = None

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


class Indexer(BaseModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    enabled: bool
    privacy: str


class Config(BaseModel, table=True):
    key: str = Field(primary_key=True)
    value: str


# TODO: add logs
class Log(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_username: str
    message: str
    timestamp: datetime = Field(default_factory=datetime.now)


class EventEnum(str, Enum):
    on_new_request = "onNewRequest"
    on_successful_download = "onSuccessfulDownload"
    on_failed_download = "onFailedDownload"


class Notification(BaseModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str
    apprise_url: str
    headers: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))
    event: EventEnum
    title_template: str
    body_template: str
    enabled: bool
