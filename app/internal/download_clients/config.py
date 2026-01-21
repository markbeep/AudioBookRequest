from typing import Literal, Optional
from sqlmodel import Session
from app.util.cache import StringConfigCache

DownloadClientConfigKey = Literal[
    "qbit_host",
    "qbit_port",
    "qbit_user",
    "qbit_pass",
    "qbit_category",
    "qbit_save_path",
    "qbit_enabled",
]

class DownloadClientConfig(StringConfigCache[DownloadClientConfigKey]):
    def get_qbit_host(self, session: Session) -> Optional[str]:
        return self.get(session, "qbit_host")

    def set_qbit_host(self, session: Session, host: str):
        self.set(session, "qbit_host", host)

    def get_qbit_port(self, session: Session) -> int:
        return self.get_int(session, "qbit_port", 8080)

    def set_qbit_port(self, session: Session, port: int):
        self.set_int(session, "qbit_port", port)

    def get_qbit_user(self, session: Session) -> Optional[str]:
        return self.get(session, "qbit_user")

    def set_qbit_user(self, session: Session, user: str):
        self.set(session, "qbit_user", user)

    def get_qbit_pass(self, session: Session) -> Optional[str]:
        return self.get(session, "qbit_pass")

    def set_qbit_pass(self, session: Session, password: str):
        self.set(session, "qbit_pass", password)

    def get_qbit_category(self, session: Session) -> str:
        return self.get(session, "qbit_category", "audiobooks")

    def set_qbit_category(self, session: Session, category: str):
        self.set(session, "qbit_category", category)

    def get_qbit_save_path(self, session: Session) -> Optional[str]:
        return self.get(session, "qbit_save_path")

    def set_qbit_save_path(self, session: Session, path: str):
        self.set(session, "qbit_save_path", path)

    def get_qbit_enabled(self, session: Session) -> bool:
        return bool(self.get_bool(session, "qbit_enabled") or False)

    def set_qbit_enabled(self, session: Session, enabled: bool):
        self.set_bool(session, "qbit_enabled", enabled)

download_client_config = DownloadClientConfig()
