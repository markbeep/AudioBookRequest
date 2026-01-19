from typing import Literal, Optional

from sqlmodel import Session

from app.util.cache import StringConfigCache


class AudiobookshelfMisconfigured(ValueError):
    pass


ABSConfigKey = Literal[
    "abs_base_url",
    "abs_api_token",
    "abs_library_id",
    "abs_check_downloaded",
]


class ABSConfig(StringConfigCache[ABSConfigKey]):
    def is_valid(self, session: Session) -> bool:
        return (
            self.get_base_url(session) is not None
            and self.get_api_token(session) is not None
            and self.get_library_id(session) is not None
            and self.get_check_downloaded(session)
        )

    def raise_if_invalid(self, session: Session):
        if not self.get_base_url(session):
            raise AudiobookshelfMisconfigured("Audiobookshelf base url not set")
        if not self.get_api_token(session):
            raise AudiobookshelfMisconfigured("Audiobookshelf API token not set")
        if not self.get_library_id(session):
            raise AudiobookshelfMisconfigured("Audiobookshelf library not selected")
        if not self.get_check_downloaded(session):
            raise AudiobookshelfMisconfigured(
                "Audiobookshelf check-downloaded disabled"
            )

    def get_base_url(self, session: Session) -> Optional[str]:
        path = self.get(session, "abs_base_url")
        if path:
            return path.rstrip("/")
        return None

    def set_base_url(self, session: Session, base_url: str):
        self.set(session, "abs_base_url", base_url)

    def get_api_token(self, session: Session) -> Optional[str]:
        return self.get(session, "abs_api_token")

    def set_api_token(self, session: Session, token: str):
        self.set(session, "abs_api_token", token)

    def get_library_id(self, session: Session) -> Optional[str]:
        return self.get(session, "abs_library_id")

    def set_library_id(self, session: Session, library_id: str):
        self.set(session, "abs_library_id", library_id)

    def get_check_downloaded(self, session: Session) -> bool:
        return bool(self.get_bool(session, "abs_check_downloaded") or False)

    def set_check_downloaded(self, session: Session, enabled: bool):
        self.set_bool(session, "abs_check_downloaded", enabled)


abs_config = ABSConfig()
