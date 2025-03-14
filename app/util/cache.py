import time
from abc import ABC
from typing import Generic, Optional, TypeVar, overload

from sqlmodel import Session, select

from app.internal.models import Config

T = TypeVar("T")


# TODO: determine if we want to use the DB as well or not
class SimpleCache(Generic[T]):
    _cache: dict[tuple[str, ...], tuple[int, T]] = {}

    def get(self, source_ttl: int, *query: str) -> Optional[T]:
        hit = self._cache.get(query)
        if not hit:
            return None
        cached_at, sources = hit
        if cached_at + source_ttl < time.time():
            return None
        return sources

    def set(self, sources: T, *query: str):
        self._cache[query] = (int(time.time()), sources)

    def flush(self):
        self._cache = {}


L = TypeVar("L", bound=str)


class StringConfigCache(Generic[L], ABC):
    _cache: dict[L, str] = {}

    @overload
    def get(self, session: Session, key: L) -> Optional[str]:
        pass

    @overload
    def get(self, session: Session, key: L, default: str) -> str:
        pass

    def get(
        self, session: Session, key: L, default: Optional[str] = None
    ) -> Optional[str]:
        if key in self._cache:
            return self._cache[key]
        return (
            session.exec(select(Config.value).where(Config.key == key)).one_or_none()
            or default
        )

    def set(self, session: Session, key: L, value: str):
        old = session.exec(select(Config).where(Config.key == key)).one_or_none()
        if old:
            old.value = value
        else:
            old = Config(key=key, value=value)
        session.add(old)
        session.commit()
        self._cache[key] = value

    def delete(self, session: Session, key: L):
        old = session.exec(select(Config).where(Config.key == key)).one_or_none()
        if old:
            session.delete(old)
            session.commit()
        if key in self._cache:
            del self._cache[key]

    @overload
    def get_int(self, session: Session, key: L) -> Optional[int]:
        pass

    @overload
    def get_int(self, session: Session, key: L, default: int) -> int:
        pass

    def get_int(
        self, session: Session, key: L, default: Optional[int] = None
    ) -> Optional[int]:
        val = self.get(session, key)
        if val:
            return int(val)
        return default

    def set_int(self, session: Session, key: L, value: int):
        self.set(session, key, str(value))
