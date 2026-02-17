from typing import Literal, Optional

from sqlmodel import Session

from app.util.cache import StringConfigCache


class ReadarrMisconfigured(ValueError):
    pass


ReadarrConfigKey = Literal[
    "readarr_base_url",
    "readarr_api_key",
    "readarr_quality_profile_id",
    "readarr_metadata_profile_id",
    "readarr_root_folder_path",
]


class ReadarrConfig(StringConfigCache[ReadarrConfigKey]):
    def is_valid(self, session: Session) -> bool:
        return (
            self.get_base_url(session) is not None
            and self.get_api_key(session) is not None
            and self.get_quality_profile_id(session) is not None
            and self.get_metadata_profile_id(session) is not None
            and self.get_root_folder_path(session) is not None
        )

    def raise_if_invalid(self, session: Session):
        if not self.get_base_url(session):
            raise ReadarrMisconfigured("Readarr base URL not set")
        if not self.get_api_key(session):
            raise ReadarrMisconfigured("Readarr API key not set")
        if not self.get_quality_profile_id(session):
            raise ReadarrMisconfigured("Readarr quality profile not set")
        if not self.get_metadata_profile_id(session):
            raise ReadarrMisconfigured("Readarr metadata profile not set")
        if not self.get_root_folder_path(session):
            raise ReadarrMisconfigured("Readarr root folder path not set")

    def get_base_url(self, session: Session) -> Optional[str]:
        path = self.get(session, "readarr_base_url")
        if path:
            return path.rstrip("/")
        return None

    def set_base_url(self, session: Session, base_url: str):
        self.set(session, "readarr_base_url", base_url)

    def get_api_key(self, session: Session) -> Optional[str]:
        return self.get(session, "readarr_api_key")

    def set_api_key(self, session: Session, api_key: str):
        self.set(session, "readarr_api_key", api_key)

    def get_quality_profile_id(self, session: Session) -> Optional[int]:
        return self.get_int(session, "readarr_quality_profile_id")

    def set_quality_profile_id(self, session: Session, profile_id: int):
        self.set_int(session, "readarr_quality_profile_id", profile_id)

    def get_metadata_profile_id(self, session: Session) -> Optional[int]:
        return self.get_int(session, "readarr_metadata_profile_id")

    def set_metadata_profile_id(self, session: Session, profile_id: int):
        self.set_int(session, "readarr_metadata_profile_id", profile_id)

    def get_root_folder_path(self, session: Session) -> Optional[str]:
        return self.get(session, "readarr_root_folder_path")

    def set_root_folder_path(self, session: Session, path: str):
        self.set(session, "readarr_root_folder_path", path)


readarr_config = ReadarrConfig()
