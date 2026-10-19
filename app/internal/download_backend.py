from typing import Literal

from sqlmodel import Session

from app.util.cache import StringConfigCache

DownloadBackend = Literal["prowlarr", "chaptarr"]
DownloadBackendKey = Literal["download_backend"]

download_backend_config = StringConfigCache[DownloadBackendKey]()


def get_download_backend(session: Session) -> DownloadBackend:
    if download_backend_config.get(session, "download_backend") == "chaptarr":
        return "chaptarr"
    return "prowlarr"


def set_download_backend(session: Session, backend: DownloadBackend):
    download_backend_config.set(session, "download_backend", backend)
