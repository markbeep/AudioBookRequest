import json
from dataclasses import dataclass
from typing import override

from pydantic import BaseModel


class _Result(BaseModel):
    id: int
    author_info: str | None = None
    narrator_info: str | None = None
    series_info: str | None = None
    language_info: str | None = None
    tags: str | None = None
    personal_freeleech: int
    free: int
    fl_vip: int
    vip: int
    filetype: str | None = None
    synopsis: str | None = None
    cover_image: str | None = None
    book_title: str | None = None
    title: str | None = None
    synopsis_image: str | None = None
    category: str | int | None = None
    added: str | None = None

    @property
    def display_title(self) -> str:
        return self.book_title or self.title or f"MAM-{self.id}"

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

    @property
    def series(self) -> list[str]:
        if not self.series_info:
            return []
        try:
            content = json.loads(self.series_info)
            if isinstance(content, dict):
                series_list = []
                for val in content.values():
                    if isinstance(val, list) and len(val) >= 2:
                        name, num = val[0], val[1]
                        series_list.append(f"{name} #{num}")
                    elif isinstance(val, str):
                        series_list.append(val)
                return series_list
        except Exception:
            pass
        return []

    @property
    def languages(self) -> list[str]:
        if not self.language_info:
            return []
        content = json.loads(self.language_info)  # pyright: ignore[reportAny]
        if isinstance(content, dict):
            return list(x for x in content.values() if isinstance(x, str))  # pyright: ignore[reportUnknownVariableType]
        return []

class _MamResponse(BaseModel):
    data: list[_Result]

