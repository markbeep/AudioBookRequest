from typing import Annotated

from aiohttp import ClientSession
from fastapi import APIRouter, Depends, Form, Request, Response, Security
from sqlmodel import Session

from app.internal.auth.authentication import ABRAuth, DetailedUser
from app.internal.audiobookshelf.client import abs_get_libraries
from app.internal.audiobookshelf.config import abs_config
from app.internal.models import GroupEnum
from app.util.connection import get_connection
from app.util.db import get_session
from app.util.templates import template_response

router = APIRouter(prefix="/audiobookshelf")


@router.get("")
async def read_abs(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    admin_user: DetailedUser = Security(ABRAuth(GroupEnum.admin)),
):
    base_url = abs_config.get_base_url(session) or ""
    api_token = abs_config.get_api_token(session) or ""
    library_id = abs_config.get_library_id(session) or ""
    check_downloaded = abs_config.get_check_downloaded(session)
    libraries = []
    if base_url and api_token:
        libraries = await abs_get_libraries(session, client_session)

    return template_response(
        "settings_page/audiobookshelf.html",
        request,
        admin_user,
        {
            "page": "audiobookshelf",
            "abs_base_url": base_url,
            "abs_api_token": api_token,
            "abs_library_id": library_id,
            "abs_check_downloaded": check_downloaded,
            "abs_libraries": libraries,
        },
    )


@router.put("/base-url")
def update_abs_base_url(
    base_url: Annotated[str, Form()],
    session: Annotated[Session, Depends(get_session)],
    admin_user: DetailedUser = Security(ABRAuth(GroupEnum.admin)),
):
    abs_config.set_base_url(session, base_url)
    return Response(status_code=204, headers={"HX-Refresh": "true"})


@router.put("/api-token")
def update_abs_api_token(
    api_token: Annotated[str, Form(alias="api_token")],
    session: Annotated[Session, Depends(get_session)],
    admin_user: DetailedUser = Security(ABRAuth(GroupEnum.admin)),
):
    abs_config.set_api_token(session, api_token)
    return Response(status_code=204, headers={"HX-Refresh": "true"})


@router.put("/library")
def update_abs_library(
    library_id: Annotated[str, Form(alias="library_id")],
    session: Annotated[Session, Depends(get_session)],
    admin_user: DetailedUser = Security(ABRAuth(GroupEnum.admin)),
):
    abs_config.set_library_id(session, library_id)
    return Response(status_code=204, headers={"HX-Refresh": "true"})


@router.put("/check-downloaded")
def update_abs_check_downloaded(
    session: Annotated[Session, Depends(get_session)],
    check_downloaded: Annotated[bool, Form()] = False,
    admin_user: DetailedUser = Security(ABRAuth(GroupEnum.admin)),
):
    abs_config.set_check_downloaded(session, check_downloaded)
    return Response(status_code=204, headers={"HX-Refresh": "true"})
