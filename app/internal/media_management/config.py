from typing import Literal, Optional
from sqlmodel import Session
from app.util.cache import StringConfigCache

MediaManagementConfigKey = Literal[
    "library_path",
    "folder_pattern",
    "file_pattern",
    "use_series_folders",
    "use_hardlinks",
    "review_before_import",
]


class MediaManagementConfig(StringConfigCache[MediaManagementConfigKey]):
    def get_library_path(self, session: Session) -> Optional[str]:
        return self.get(session, "library_path")

    def set_library_path(self, session: Session, path: str):
        self.set(session, "library_path", path)

    def get_folder_pattern(self, session: Session) -> str:
        return self.get(session, "folder_pattern", "{author}/{title} ({year})")

    def set_folder_pattern(self, session: Session, pattern: str):
        self.set(session, "folder_pattern", pattern)

    def get_file_pattern(self, session: Session) -> str:
        return self.get(session, "file_pattern", "{title}-{year}-{part}")

    def set_file_pattern(self, session: Session, pattern: str):
        self.set(session, "file_pattern", pattern)

    def get_use_series_folders(self, session: Session) -> bool:
        return bool(self.get_bool(session, "use_series_folders") or False)

    def set_use_series_folders(self, session: Session, enabled: bool):
        self.set_bool(session, "use_series_folders", enabled)

    def get_use_hardlinks(self, session: Session) -> bool:
        return bool(self.get_bool(session, "use_hardlinks") or False)

    def set_use_hardlinks(self, session: Session, enabled: bool):
        self.set_bool(session, "use_hardlinks", enabled)

    def get_review_before_import(self, session: Session) -> bool:
        return bool(self.get_bool(session, "review_before_import") or False)

    def set_review_before_import(self, session: Session, enabled: bool):
        self.set_bool(session, "review_before_import", enabled)


media_management_config = MediaManagementConfig()
