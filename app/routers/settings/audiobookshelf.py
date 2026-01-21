from typing import Annotated, Optional

from aiohttp import ClientSession
from fastapi import APIRouter, Depends, Form, Request, Response, Security
from sqlmodel import Session

from app.internal.auth.authentication import ABRAuth, DetailedUser
from app.internal.models import GroupEnum
from app.util.connection import get_connection
from app.util.db import get_session
from app.util.templates import template_response
from app.routers.api.settings.audiobookshelf import (
    read_abs as api_read_abs,
    update_abs_base_url as api_update_abs_base_url,
    update_abs_api_token as api_update_abs_api_token,
    update_abs_library as api_update_abs_library,
    update_abs_check_downloaded as api_update_abs_check_downloaded,
)

router = APIRouter(prefix="/audiobookshelf")


@router.get("")
async def read_abs(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    response = await api_read_abs(
        session=session,
        client_session=client_session,
        admin_user=admin_user,
    )
    return template_response(
        "settings_page/audiobookshelf.html",
        request,
        admin_user,
        {
            "page": "audiobookshelf",
            "abs_base_url": response.abs_base_url,
            "abs_api_token": response.abs_api_token,
            "abs_library_id": response.abs_library_id,
            "abs_check_downloaded": response.abs_check_downloaded,
            "abs_libraries": response.abs_libraries,
        },
    )


@router.put("/base-url")
def update_abs_base_url(
    base_url: Annotated[str, Form()],
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    api_update_abs_base_url(base_url=base_url, session=session, admin_user=admin_user)
    return Response(status_code=204, headers={"HX-Refresh": "true"})


@router.put("/api-token")
def update_abs_api_token(
    api_token: Annotated[str, Form(alias="api_token")],
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    api_update_abs_api_token(
        api_token=api_token, session=session, admin_user=admin_user
    )
    return Response(status_code=204, headers={"HX-Refresh": "true"})


@router.put("/library")
def update_abs_library(
    library_id: Annotated[str, Form(alias="library_id")],
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    api_update_abs_library(
        library_id=library_id, session=session, admin_user=admin_user
    )
    return Response(status_code=204, headers={"HX-Refresh": "true"})


@router.put("/check-downloaded")
def update_abs_check_downloaded(
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
    check_downloaded: Annotated[bool, Form()] = False,
):
    api_update_abs_check_downloaded(
        session=session,
        admin_user=admin_user,
        check_downloaded=check_downloaded,
    )
    return Response(status_code=204, headers={"HX-Refresh": "true"})

@router.post("/test")
async def test_abs(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
    base_url: Annotated[Optional[str], Form()] = None,
    api_token: Annotated[Optional[str], Form()] = None,
):
    from app.internal.audiobookshelf.client import abs_get_libraries
    from app.internal.audiobookshelf.config import abs_config
    
    # Temporarily override config for the test if values provided
    if base_url:
        abs_config.set_base_url(session, base_url)
    if api_token and api_token != "":
        abs_config.set_api_token(session, api_token)

    try:
        libs = await abs_get_libraries(session, client_session)
        if libs:
            return template_response(
                "base.html",
                request,
                None,
                {"toast_success": f"ABS connection successful! Found {len(libs)} libraries."},
                headers={"HX-Retarget": "#toast-block", "HX-Reswap": "innerHTML"},
                block_name="toast_block"
            )
        else:
            return template_response(
                "base.html",
                request,
                None,
                {"toast_info": "ABS connection successful, but no libraries found."},
                headers={"HX-Retarget": "#toast-block", "HX-Reswap": "innerHTML"},
                block_name="toast_block"
            )
    except Exception as e:
        return template_response(
            "scripts/toast.html",
            request,
            None,
            {"message": f"ABS connection failed: {str(e)}", "type": "error"},
        )
