import json
from typing import Literal, final

import pydantic
from pydantic_core import from_json, to_json
from sqlmodel import Session

from app.util.cache import StringConfigCache

QualityFormatKey = Literal[
    "quality_flac",
    "quality_m4b",
    "quality_mp3",
    "quality_unknown_audio",
    "quality_unknown",
]

QualityConfigKey = (
    QualityFormatKey
    | Literal[
        "quality_auto_download",
        "quality_indexer_flags",
        "quality_format_order",
        "quality_indexer_order",
        "quality_name_exists_ratio",
        "quality_title_exists_ratio",
        "quality_min_seeders",
    ]
)
FileFormat = Literal["flac", "m4b", "mp3", "unknown-audio", "unknown"]


class QualityRange(pydantic.BaseModel):
    from_kbits: float
    to_kbits: float


CompareType = Literal[
    "valid",
    "title",
    "authors",
    "narrators",
    "format",
    "flags",
    "indexer",
    "subtitle",
    "seeders",
]


class IndexerFlag(pydantic.BaseModel):
    flag: str
    score: int


@final
class QualityProfile(StringConfigCache[QualityConfigKey]):
    _default_quality_range = QualityRange(from_kbits=20.0, to_kbits=400.0)
    _default_name_exists_ratio: int = 75
    _default_title_exists_ratio: int = 90
    _default_min_seeders = 2

    def reset_all(self, session: Session):
        # TODO: find a way so values don't have to be repeated here
        keys: list[QualityConfigKey] = [
            "quality_flac",
            "quality_m4b",
            "quality_mp3",
            "quality_unknown_audio",
            "quality_unknown",
            "quality_auto_download",
            "quality_indexer_flags",
            "quality_format_order",
            "quality_indexer_order",
            "quality_name_exists_ratio",
            "quality_title_exists_ratio",
            "quality_min_seeders",
        ]
        for key in keys:
            self.delete(session, key)

    def get_auto_download(self, session: Session) -> bool:
        return bool(self.get_int(session, "quality_auto_download", 0))

    def set_auto_download(self, session: Session, auto_download: bool):
        self.set_int(session, "quality_auto_download", int(auto_download))

    def get_range(self, session: Session, key: QualityFormatKey) -> QualityRange:
        range = self.get(session, key)
        if not range:
            return self._default_quality_range
        from_kbits, to_kbits = range.split(",", maxsplit=1)
        return QualityRange(from_kbits=float(from_kbits), to_kbits=float(to_kbits))

    def set_range(self, session: Session, key: QualityFormatKey, range: QualityRange):
        self.set(session, key, f"{range.from_kbits},{range.to_kbits}")

    def get_indexer_flags(self, session: Session) -> list[IndexerFlag]:
        indexer_flags = self.get(session, "quality_indexer_flags")
        if not indexer_flags:
            return []
        flags = from_json(indexer_flags.encode())  # pyright: ignore[reportAny]
        return [IndexerFlag.model_validate(flag) for flag in flags]  # pyright: ignore[reportAny]

    def set_indexer_flags(self, session: Session, indexer_flags: list[IndexerFlag]):
        self.set(session, "quality_indexer_flags", to_json(indexer_flags).decode())

    def get_format_order(self, session: Session) -> list[FileFormat]:
        format_order = self.get(session, "quality_format_order")
        if not format_order:
            return ["flac", "m4b", "mp3", "unknown-audio", "unknown"]
        return json.loads(format_order)  # pyright: ignore[reportAny]

    def set_format_order(self, session: Session, format_order: list[FileFormat]):
        self.set(session, "quality_format_order", json.dumps(format_order))

    def get_indexer_order(self, session: Session) -> list[int]:
        indexer_order = self.get(session, "quality_indexer_order")
        if not indexer_order:
            return []
        return json.loads(indexer_order)  # pyright: ignore[reportAny]

    def set_indexer_order(self, session: Session, format_order: list[int]):
        self.set(session, "quality_indexer_order", json.dumps(format_order))

    def get_name_exists_ratio(self, session: Session) -> int:
        return self.get_int(
            session, "quality_name_exists_ratio", self._default_name_exists_ratio
        )

    def set_name_exists_ratio(self, session: Session, name_exists_ratio: int):
        self.set_int(session, "quality_name_exists_ratio", name_exists_ratio)

    def get_title_exists_ratio(self, session: Session) -> int:
        return self.get_int(
            session, "quality_title_exists_ratio", self._default_title_exists_ratio
        )

    def set_title_exists_ratio(self, session: Session, title_exists_ratio: int):
        self.set_int(session, "quality_title_exists_ratio", title_exists_ratio)

    def get_min_seeders(self, session: Session) -> int:
        return self.get_int(session, "quality_min_seeders", self._default_min_seeders)

    def set_min_seeders(self, session: Session, min_seeders: int):
        self.set_int(session, "quality_min_seeders", min_seeders)

    def calculate_quality_rank(self, session: Session, file_format: FileFormat) -> int:
        format_order = self.get_format_order(session)
        try:
            return format_order.index(file_format)
        except ValueError:
            return len(format_order)

    def calculate_indexer_rank(self, session: Session, indexer_id: int) -> int:
        indexer_order = self.get_indexer_order(session)
        try:
            return indexer_order.index(indexer_id)
        except ValueError:
            return len(indexer_order)


quality_config = QualityProfile()
