from typing import Annotated

from aiohttp import ClientSession
from fastapi import APIRouter, Depends, Response, Security
from pydantic import BaseModel
from sqlmodel import Session

from app.internal.auth.authentication import AnyAuth, DetailedUser
from app.internal.chaptarr.client import chaptarr_connected
from app.internal.chaptarr.config import chaptarr_config
from app.internal.models import GroupEnum
from app.util.connection import get_connection
from app.util.db import get_session

router = APIRouter(prefix="/chaptarr")


class ChaptarrSettings(BaseModel):
    base_url: str
    api_key: str
    connected: bool


@router.get("", response_model=ChaptarrSettings)
async def read_chaptarr(
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    _: Annotated[DetailedUser, Security(AnyAuth(GroupEnum.admin))],
):
    return ChaptarrSettings(
        base_url=chaptarr_config.get_base_url(session) or "",
        api_key=chaptarr_config.get_api_key(session) or "",
        connected=await chaptarr_connected(session, client_session),
    )


class UpdateBaseUrl(BaseModel):
    base_url: str


@router.put("/base-url", status_code=204)
def update_chaptarr_base_url(
    body: UpdateBaseUrl,
    session: Annotated[Session, Depends(get_session)],
    _: Annotated[DetailedUser, Security(AnyAuth(GroupEnum.admin))],
):
    chaptarr_config.set_base_url(session, body.base_url)
    return Response(status_code=204)


class UpdateApiKey(BaseModel):
    api_key: str


@router.put("/api-key", status_code=204)
def update_chaptarr_api_key(
    body: UpdateApiKey,
    session: Annotated[Session, Depends(get_session)],
    _: Annotated[DetailedUser, Security(AnyAuth(GroupEnum.admin))],
):
    chaptarr_config.set_api_key(session, body.api_key)
    return Response(status_code=204)
