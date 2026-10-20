from typing import Annotated

from aiohttp import ClientSession
from fastapi import APIRouter, Depends, Form, Response, Security
from sqlmodel import Session

from app.internal.audiobookshelf.config import abs_config
from app.internal.auth.authentication import ABRAuth, DetailedUser
from app.internal.models import GroupEnum
from app.routers.api.settings.audiobookshelf import (
    read_abs as api_read_abs,
)
from app.util.connection import get_connection
from app.util.db import get_session
from app.util.templates import catalog_response

router = APIRouter(prefix="/audiobookshelf")


@router.get("")
async def read_abs(
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    response = await api_read_abs(
        session=session,
        client_session=client_session,
        admin_user=admin_user,
    )

    return catalog_response(
        "Settings.Audiobookshelf",
        user=admin_user,
        abs_base_url=response.abs_base_url,
        abs_api_token=response.abs_api_token,
        abs_library_id=response.abs_library_id,
        abs_check_downloaded=response.abs_check_downloaded,
        abs_libraries=response.abs_libraries,
    )


@router.put("/hx-base-url")
def update_abs_base_url(
    base_url: Annotated[str, Form()],
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    _ = admin_user
    abs_config.set_base_url(session, base_url)
    return Response(status_code=204, headers={"HX-Refresh": "true"})


@router.put("/hx-api-token")
def update_abs_api_token(
    api_token: Annotated[str, Form(alias="api_token")],
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    _ = admin_user
    abs_config.set_api_token(session, api_token)
    return Response(status_code=204, headers={"HX-Refresh": "true"})


@router.put("/hx-library")
def update_abs_library(
    library_id: Annotated[str, Form(alias="library_id")],
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    _ = admin_user
    abs_config.set_library_id(session, library_id)
    return Response(status_code=204, headers={"HX-Refresh": "true"})


@router.put("/hx-check-downloaded")
def update_abs_check_downloaded(
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
    check_downloaded: Annotated[bool, Form()] = False,
):
    _ = admin_user
    abs_config.set_check_downloaded(session, check_downloaded)
    return Response(status_code=204, headers={"HX-Refresh": "true"})
