from fastapi import APIRouter

from . import for_you

router = APIRouter(prefix="/recommendations")

router.include_router(for_you.router)
