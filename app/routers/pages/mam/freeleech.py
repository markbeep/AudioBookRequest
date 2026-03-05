from typing import Annotated

from aiohttp import ClientSession
from fastapi import APIRouter, Depends, HTTPException, Security, status
from sqlmodel import Session

from app.internal.auth.authentication import ABRAuth, DetailedUser
from app.internal.mam.config import mam_freeleech_config
from app.internal.mam.freeleech import fetch_mam_freeleech
from app.internal.models import GroupEnum
from app.util.connection import get_connection
from app.util.db import get_session
from app.util.templates import catalog_response

router = APIRouter()


@router.get("")
async def get_freeleech_page(
    db_session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.trusted))],
    force_refresh: bool = False,
):
    """
    The MaM Freeleech browse page.

    Accessible to Trusted and Admin users. Admin can restrict it to Admin-only
    via the mam_freeleech_trusted_visible setting.
    """
    if not user.is_admin() and not mam_freeleech_config.get_trusted_visible(db_session):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Freeleech page is currently restricted to admins.",
        )

    ttl = mam_freeleech_config.get_ttl_seconds(db_session)

    result = await fetch_mam_freeleech(
        db_session=db_session,
        client_session=client_session,
        ttl_seconds=ttl,
        force_refresh=force_refresh,
    )

    return catalog_response(
        "Freeleech.Index",
        user=user,
        result=result,
        ttl_minutes=ttl // 60,
    )
