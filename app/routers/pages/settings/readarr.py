from typing import Annotated

from aiohttp import ClientSession
from fastapi import APIRouter, Depends, Form, Response, Security
from sqlmodel import Session

from app.internal.auth.authentication import ABRAuth, DetailedUser
from app.internal.models import GroupEnum
from app.routers.api.settings.readarr import (
    read_readarr as api_read_readarr,
)
from app.routers.api.settings.readarr import (
    update_readarr_api_key as api_update_readarr_api_key,
)
from app.routers.api.settings.readarr import (
    update_readarr_base_url as api_update_readarr_base_url,
)
from app.routers.api.settings.readarr import (
    update_readarr_metadata_profile as api_update_readarr_metadata_profile,
)
from app.routers.api.settings.readarr import (
    update_readarr_quality_profile as api_update_readarr_quality_profile,
)
from app.routers.api.settings.readarr import (
    update_readarr_root_folder as api_update_readarr_root_folder,
)
from app.util.connection import get_connection
from app.util.db import get_session
from app.util.templates import catalog_response

router = APIRouter(prefix="/readarr")


@router.get("")
async def read_readarr(
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    response = await api_read_readarr(
        session=session,
        client_session=client_session,
        admin_user=admin_user,
    )

    return catalog_response(
        "Settings.Readarr",
        user=admin_user,
        readarr_base_url=response.readarr_base_url,
        readarr_api_key=response.readarr_api_key,
        readarr_quality_profile_id=response.readarr_quality_profile_id,
        readarr_metadata_profile_id=response.readarr_metadata_profile_id,
        readarr_root_folder_path=response.readarr_root_folder_path,
        quality_profiles=response.quality_profiles,
        metadata_profiles=response.metadata_profiles,
        root_folders=response.root_folders,
    )


@router.put("/hx-base-url")
def update_readarr_base_url(
    base_url: Annotated[str, Form()],
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    api_update_readarr_base_url(
        base_url=base_url, session=session, admin_user=admin_user
    )
    return Response(status_code=204, headers={"HX-Refresh": "true"})


@router.put("/hx-api-key")
def update_readarr_api_key(
    api_key: Annotated[str, Form(alias="api_key")],
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    api_update_readarr_api_key(api_key=api_key, session=session, admin_user=admin_user)
    return Response(status_code=204, headers={"HX-Refresh": "true"})


@router.put("/hx-quality-profile")
def update_readarr_quality_profile(
    quality_profile_id: Annotated[int, Form(alias="quality_profile_id")],
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    api_update_readarr_quality_profile(
        quality_profile_id=quality_profile_id, session=session, admin_user=admin_user
    )
    return Response(status_code=204, headers={"HX-Refresh": "true"})


@router.put("/hx-metadata-profile")
def update_readarr_metadata_profile(
    metadata_profile_id: Annotated[int, Form(alias="metadata_profile_id")],
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    api_update_readarr_metadata_profile(
        metadata_profile_id=metadata_profile_id, session=session, admin_user=admin_user
    )
    return Response(status_code=204, headers={"HX-Refresh": "true"})


@router.put("/hx-root-folder")
def update_readarr_root_folder(
    root_folder_path: Annotated[str, Form(alias="root_folder_path")],
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    api_update_readarr_root_folder(
        root_folder_path=root_folder_path, session=session, admin_user=admin_user
    )
    return Response(status_code=204, headers={"HX-Refresh": "true"})
