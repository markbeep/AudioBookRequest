from fastapi import APIRouter

from . import freeleech

router = APIRouter(prefix="/freeleech")

router.include_router(freeleech.router)
