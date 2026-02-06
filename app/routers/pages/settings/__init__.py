from fastapi import APIRouter

from . import (
    account,
    audiobookshelf,
    download,
    indexers,
    notification,
    prowlarr,
    security,
    users,
)

router = APIRouter(prefix="/settings")

router.include_router(account.router)
router.include_router(audiobookshelf.router)
router.include_router(download.router)
router.include_router(indexers.router)
router.include_router(notification.router)
router.include_router(prowlarr.router)
router.include_router(security.router)
router.include_router(users.router)
