from typing import Literal

from sqlmodel import Session

from app.util.cache import StringConfigCache


class ChaptarrMisconfigured(ValueError):
    pass


ChaptarrConfigKey = Literal["chaptarr_base_url", "chaptarr_api_key"]


class ChaptarrConfig(StringConfigCache[ChaptarrConfigKey]):
    def is_valid(self, session: Session) -> bool:
        return (
            self.get_base_url(session) is not None
            and self.get_api_key(session) is not None
        )

    def raise_if_invalid(self, session: Session):
        if not self.get_base_url(session):
            raise ChaptarrMisconfigured("Chaptarr base url not set")
        if not self.get_api_key(session):
            raise ChaptarrMisconfigured("Chaptarr API key not set")

    def get_base_url(self, session: Session) -> str | None:
        path = self.get(session, "chaptarr_base_url")
        if path:
            return path.rstrip("/")
        return None

    def set_base_url(self, session: Session, base_url: str):
        self.set(session, "chaptarr_base_url", base_url)

    def get_api_key(self, session: Session) -> str | None:
        return self.get(session, "chaptarr_api_key")

    def set_api_key(self, session: Session, api_key: str):
        self.set(session, "chaptarr_api_key", api_key)


chaptarr_config = ChaptarrConfig()
