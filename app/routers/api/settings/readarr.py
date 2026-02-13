from typing import Annotated

from aiohttp import ClientSession
from fastapi import APIRouter, Depends, Form, HTTPException, Response, Security
from pydantic import BaseModel
from sqlmodel import Session

from app.internal.auth.authentication import AnyAuth, DetailedUser
from app.internal.models import GroupEnum
from app.internal.readarr.client import (
    readarr_get_metadata_profiles,
    readarr_get_quality_profiles,
    readarr_get_root_folders,
)
from app.internal.readarr.config import readarr_config
from app.internal.readarr.types import (
    ReadarrMetadataProfile,
    ReadarrQualityProfile,
    ReadarrRootFolder,
)
from app.util.connection import get_connection
from app.util.db import get_session
from app.util.log import logger

router = APIRouter(prefix="/readarr")


class ReadarrResponse(BaseModel):
    readarr_base_url: str
    readarr_api_key: str
    readarr_quality_profile_id: int | None
    readarr_metadata_profile_id: int | None
    readarr_root_folder_path: str
    quality_profiles: list[ReadarrQualityProfile]
    metadata_profiles: list[ReadarrMetadataProfile]
    root_folders: list[ReadarrRootFolder]


@router.get("")
async def read_readarr(
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    admin_user: Annotated[DetailedUser, Security(AnyAuth(GroupEnum.admin))],
):
    _ = admin_user
    base_url = readarr_config.get_base_url(session) or ""
    api_key = readarr_config.get_api_key(session) or ""
    quality_profile_id = readarr_config.get_quality_profile_id(session)
    metadata_profile_id = readarr_config.get_metadata_profile_id(session)
    root_folder_path = readarr_config.get_root_folder_path(session) or ""

    quality_profiles: list[ReadarrQualityProfile] = []
    metadata_profiles: list[ReadarrMetadataProfile] = []
    root_folders: list[ReadarrRootFolder] = []
    if base_url and api_key:
        quality_profiles = await readarr_get_quality_profiles(session, client_session)
        metadata_profiles = await readarr_get_metadata_profiles(session, client_session)
        root_folders = await readarr_get_root_folders(session, client_session)

    return ReadarrResponse(
        readarr_base_url=base_url,
        readarr_api_key=api_key,
        readarr_quality_profile_id=quality_profile_id,
        readarr_metadata_profile_id=metadata_profile_id,
        readarr_root_folder_path=root_folder_path,
        quality_profiles=quality_profiles,
        metadata_profiles=metadata_profiles,
        root_folders=root_folders,
    )


@router.put("/base-url")
def update_readarr_base_url(
    base_url: Annotated[str, Form()],
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(AnyAuth(GroupEnum.admin))],
):
    _ = admin_user
    readarr_config.set_base_url(session, base_url)
    return Response(status_code=204)


@router.put("/api-key")
def update_readarr_api_key(
    api_key: Annotated[str, Form(alias="api_key")],
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(AnyAuth(GroupEnum.admin))],
):
    _ = admin_user
    readarr_config.set_api_key(session, api_key)
    return Response(status_code=204)


@router.put("/quality-profile")
def update_readarr_quality_profile(
    quality_profile_id: Annotated[int, Form(alias="quality_profile_id")],
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(AnyAuth(GroupEnum.admin))],
):
    _ = admin_user
    readarr_config.set_quality_profile_id(session, quality_profile_id)
    return Response(status_code=204)


@router.put("/metadata-profile")
def update_readarr_metadata_profile(
    metadata_profile_id: Annotated[int, Form(alias="metadata_profile_id")],
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(AnyAuth(GroupEnum.admin))],
):
    _ = admin_user
    readarr_config.set_metadata_profile_id(session, metadata_profile_id)
    return Response(status_code=204)


@router.put("/root-folder")
def update_readarr_root_folder(
    root_folder_path: Annotated[str, Form(alias="root_folder_path")],
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(AnyAuth(GroupEnum.admin))],
):
    _ = admin_user
    readarr_config.set_root_folder_path(session, root_folder_path)
    return Response(status_code=204)


class ReadarrTestResponse(BaseModel):
    quality_profile_count: int
    metadata_profile_count: int
    root_folder_count: int


@router.get("/test-connection")
async def test_readarr_connection(
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    _: Annotated[DetailedUser, Security(AnyAuth(GroupEnum.admin))],
):
    base_url = readarr_config.get_base_url(session)
    api_key = readarr_config.get_api_key(session)
    if not base_url or not api_key:
        raise HTTPException(
            status_code=400, detail="Readarr base URL and API key are required"
        )

    quality_profiles = await readarr_get_quality_profiles(session, client_session)
    if not quality_profiles:
        raise HTTPException(
            status_code=400,
            detail="Failed to connect to Readarr — could not fetch quality profiles",
        )
    metadata_profiles = await readarr_get_metadata_profiles(session, client_session)
    root_folders = await readarr_get_root_folders(session, client_session)

    logger.info(
        "Readarr: test connection successful",
        quality_profiles=len(quality_profiles),
        metadata_profiles=len(metadata_profiles),
        root_folders=len(root_folders),
    )

    return ReadarrTestResponse(
        quality_profile_count=len(quality_profiles),
        metadata_profile_count=len(metadata_profiles),
        root_folder_count=len(root_folders),
    )
