from fastapi import APIRouter

from . import login, logout, oidc

router = APIRouter(prefix="/auth")

router.include_router(login.router)
router.include_router(logout.router)
router.include_router(oidc.router)
