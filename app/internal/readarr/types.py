from pydantic import BaseModel, ConfigDict


# --- Settings API models (used by settings page dropdowns) ---


class ReadarrQualityProfile(BaseModel):
    id: int
    name: str


class ReadarrMetadataProfile(BaseModel):
    id: int
    name: str


class ReadarrRootFolder(BaseModel):
    model_config = ConfigDict(extra="allow")  # pyright: ignore[reportUnannotatedClassAttribute]
    id: int = 0
    path: str
    name: str = ""


# --- Search / Add API models (used internally for book matching) ---


class ReadarrAuthorAddOptions(BaseModel):
    model_config = ConfigDict(extra="allow")  # pyright: ignore[reportUnannotatedClassAttribute]
    monitor: str = "all"
    searchForMissingBooks: bool = False


class ReadarrBookAddOptions(BaseModel):
    model_config = ConfigDict(extra="allow")  # pyright: ignore[reportUnannotatedClassAttribute]
    searchForNewBook: bool = False


class ReadarrAuthor(BaseModel):
    model_config = ConfigDict(extra="allow")  # pyright: ignore[reportUnannotatedClassAttribute]
    authorName: str = ""
    foreignAuthorId: str = ""
    qualityProfileId: int | None = None
    metadataProfileId: int | None = None
    rootFolderPath: str | None = None
    monitored: bool = False
    addOptions: ReadarrAuthorAddOptions | None = None


class ReadarrBook(BaseModel):
    model_config = ConfigDict(extra="allow")  # pyright: ignore[reportUnannotatedClassAttribute]
    id: int = 0
    title: str = ""
    foreignBookId: str = ""
    author: ReadarrAuthor | None = None
    monitored: bool = False
    addOptions: ReadarrBookAddOptions | None = None


class ReadarrSearchResult(BaseModel):
    model_config = ConfigDict(extra="allow")  # pyright: ignore[reportUnannotatedClassAttribute]
    book: ReadarrBook | None = None
