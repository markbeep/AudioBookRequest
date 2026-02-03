from typing import Annotated

from aiohttp import ClientSession
from fastapi import APIRouter, Depends, Response, Security
from pydantic import BaseModel
from sqlmodel import Session

from app.internal.auth.authentication import AnyAuth, DetailedUser
from app.internal.models import GroupEnum
from app.internal.prowlarr.indexer_categories import indexer_categories
from app.internal.prowlarr.prowlarr import IndexerResponse, get_indexers
from app.internal.prowlarr.util import flush_prowlarr_cache, prowlarr_config
from app.util.connection import get_connection
from app.util.db import get_session

router = APIRouter(prefix="/prowlarr")


class ProwlarrSettings(BaseModel):
    base_url: str
    api_key: str
    selected_categories: list[int]
    selected_indexers: list[int]
    all_categories: dict[int, str]
    indexers: IndexerResponse


@router.get("", response_model=ProwlarrSettings)
async def get_prowlarr_settings(
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    _: Annotated[DetailedUser, Security(AnyAuth(GroupEnum.admin))],
):
    indexers = await get_indexers(session, client_session)
    return ProwlarrSettings(
        base_url=prowlarr_config.get_base_url(session) or "",
        api_key=prowlarr_config.get_api_key(session) or "",
        selected_categories=prowlarr_config.get_categories(session),
        selected_indexers=prowlarr_config.get_indexers(session),
        all_categories=indexer_categories,
        indexers=indexers,
    )


class UpdateApiKey(BaseModel):
    api_key: str


@router.put("/api-key", status_code=204)
def update_prowlarr_api_key(
    body: UpdateApiKey,
    session: Annotated[Session, Depends(get_session)],
    _: Annotated[DetailedUser, Security(AnyAuth(GroupEnum.admin))],
):
    prowlarr_config.set_api_key(session, body.api_key)
    flush_prowlarr_cache()
    return Response(status_code=204)


class UpdateBaseUrl(BaseModel):
    base_url: str


@router.put("/base-url", status_code=204)
def update_prowlarr_base_url(
    body: UpdateBaseUrl,
    session: Annotated[Session, Depends(get_session)],
    _: Annotated[DetailedUser, Security(AnyAuth(GroupEnum.admin))],
):
    prowlarr_config.set_base_url(session, body.base_url)
    flush_prowlarr_cache()
    return Response(status_code=204)


class UpdateCategories(BaseModel):
    categories: list[int]


@router.put("/categories", status_code=204)
def update_indexer_categories(
    body: UpdateCategories,
    session: Annotated[Session, Depends(get_session)],
    _: Annotated[DetailedUser, Security(AnyAuth(GroupEnum.admin))],
):
    prowlarr_config.set_categories(session, body.categories)
    flush_prowlarr_cache()
    return Response(status_code=204)
