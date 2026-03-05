from typing import Annotated

from aiohttp import ClientSession
from fastapi import APIRouter, Depends, Security
from sqlmodel import Session

from app.internal.auth.authentication import AnyAuth, DetailedUser
from app.internal.mam.config import mam_freeleech_config
from app.internal.mam.freeleech import MamFreeleechResult, fetch_mam_freeleech
from app.internal.models import GroupEnum
from app.util.connection import get_connection
from app.util.db import get_session

router = APIRouter(prefix="/mam", tags=["MaM"])


@router.get("/freeleech", response_model=MamFreeleechResult)
async def get_mam_freeleech(
    db_session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    user: Annotated[DetailedUser, Security(AnyAuth(GroupEnum.trusted))],
    force_refresh: bool = False,
) -> MamFreeleechResult:
    """
    Return current freeleech audiobooks from MaM.

    Results are cached for the configured TTL (default 15 minutes).
    Pass force_refresh=true to bypass the cache.
    Requires Trusted or Admin role.
    """
    ttl = mam_freeleech_config.get_ttl_seconds(db_session)

    # Admins can always see freeleech; Trusted users only if the setting allows
    if not user.is_admin():
        if not mam_freeleech_config.get_trusted_visible(db_session):
            from fastapi import HTTPException, status

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Freeleech page is currently restricted to admins.",
            )

    return await fetch_mam_freeleech(
        db_session=db_session,
        client_session=client_session,
        ttl_seconds=ttl,
        force_refresh=force_refresh,
    )
