from typing import Annotated

from fastapi import APIRouter, Depends, Form, Response, Security
from sqlmodel import Session

from app.internal.auth.authentication import ABRAuth, DetailedUser
from app.internal.indexers.configuration import indexer_configuration_cache
from app.internal.mam.config import mam_freeleech_config
from app.internal.mam.freeleech import flush_freeleech_cache
from app.internal.models import GroupEnum
from app.util.db import get_session
from app.util.templates import catalog_response, catalog_response_toast

router = APIRouter(prefix="/mam")


@router.get("")
def read_mam_settings(
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    mam_session_id = indexer_configuration_cache.get(session, "mam_session_id")
    ttl_minutes = mam_freeleech_config.get_ttl_seconds(session) // 60
    trusted_visible = mam_freeleech_config.get_trusted_visible(session)

    return catalog_response(
        "Settings.Mam",
        user=admin_user,
        page="mam",
        mam_session_id_set=bool(mam_session_id),
        ttl_minutes=ttl_minutes,
        trusted_visible=trusted_visible,
    )


@router.put("/hx-session-id", status_code=204)
def update_mam_session_id(
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
    mam_session_id: Annotated[str, Form()],
):
    _ = admin_user
    indexer_configuration_cache.set(session, "mam_session_id", mam_session_id)
    flush_freeleech_cache()
    return Response(status_code=204, headers={"HX-Refresh": "true"})


@router.put("/hx-ttl", status_code=204)
def update_mam_ttl(
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
    ttl_minutes: Annotated[int, Form()],
):
    _ = admin_user
    mam_freeleech_config.set_ttl_seconds(session, max(1, ttl_minutes) * 60)
    flush_freeleech_cache()
    return Response(status_code=204, headers={"HX-Refresh": "true"})


@router.post("/hx-trusted-toggle")
def toggle_trusted_visible(
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
    trusted_visible: Annotated[bool, Form()] = False,
):
    _ = admin_user
    mam_freeleech_config.set_trusted_visible(session, trusted_visible)
    return Response(status_code=204, headers={"HX-Refresh": "true"})
