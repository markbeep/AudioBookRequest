from typing import Annotated

from aiohttp import ClientSession
from fastapi import APIRouter, Depends, Form, Response, Security
from sqlmodel import Session

from app.internal.auth.authentication import ABRAuth, DetailedUser
from app.internal.chaptarr.client import chaptarr_connected
from app.internal.chaptarr.config import chaptarr_config
from app.internal.download_backend import DownloadBackend, get_download_backend
from app.internal.models import GroupEnum
from app.internal.prowlarr.indexer_categories import indexer_categories
from app.internal.prowlarr.prowlarr import IndexerResponse, get_indexers
from app.internal.prowlarr.util import flush_prowlarr_cache, prowlarr_config
from app.routers.api.settings.prowlarr import (
    UpdateApiKey,
    UpdateBackend,
    UpdateBaseUrl,
    UpdateCategories,
)
from app.routers.api.settings.prowlarr import (
    update_download_backend as api_update_download_backend,
)
from app.routers.api.settings.prowlarr import (
    update_indexer_categories as api_update_indexer_categories,
)
from app.routers.api.settings.prowlarr import (
    update_prowlarr_api_key as api_update_prowlarr_api_key,
)
from app.routers.api.settings.prowlarr import (
    update_prowlarr_base_url as api_update_prowlarr_base_url,
)
from app.util.connection import get_connection
from app.util.db import get_session
from app.util.templates import catalog_response, catalog_response_toast

router = APIRouter(prefix="/prowlarr")


@router.get("")
async def read_prowlarr(
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
    prowlarr_misconfigured: object | None = None,
):
    download_backend = get_download_backend(session)
    prowlarr_base_url = prowlarr_config.get_base_url(session)
    prowlarr_api_key = prowlarr_config.get_api_key(session)
    selected = set(prowlarr_config.get_categories(session))
    selected_indexers = set(prowlarr_config.get_indexers(session))
    chaptarr_base_url = chaptarr_config.get_base_url(session) or ""
    chaptarr_api_key = chaptarr_config.get_api_key(session) or ""

    if download_backend == "prowlarr":
        indexers = await get_indexers(session, client_session)
        connected = False
    else:
        indexers = IndexerResponse(state="failedFetch")
        connected = await chaptarr_connected(session, client_session)

    return catalog_response(
        "Settings.Prowlarr.Index",
        user=admin_user,
        download_backend=download_backend,
        prowlarr_base_url=prowlarr_base_url,
        prowlarr_api_key=prowlarr_api_key,
        indexer_categories=indexer_categories,
        selected_categories=selected,
        indexers=indexers,
        selected_indexers=selected_indexers,
        prowlarr_misconfigured=bool(prowlarr_misconfigured),
        chaptarr_base_url=chaptarr_base_url,
        chaptarr_api_key=chaptarr_api_key,
        chaptarr_configured=chaptarr_config.is_valid(session),
        chaptarr_connected=connected,
    )


@router.put("/hx-backend")
def update_download_backend(
    backend: Annotated[DownloadBackend, Form()],
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    api_update_download_backend(UpdateBackend(backend=backend), session, admin_user)
    return Response(status_code=204, headers={"HX-Refresh": "true"})


@router.put("/hx-api-key")
def update_prowlarr_api_key(
    api_key: Annotated[str, Form()],
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    api_update_prowlarr_api_key(UpdateApiKey(api_key=api_key), session, admin_user)
    return Response(status_code=204, headers={"HX-Refresh": "true"})


@router.put("/hx-base-url")
def update_prowlarr_base_url(
    base_url: Annotated[str, Form()],
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    api_update_prowlarr_base_url(UpdateBaseUrl(base_url=base_url), session, admin_user)
    return Response(status_code=204, headers={"HX-Refresh": "true"})


@router.put("/hx-category")
def update_indexer_categories(
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
    categories: Annotated[list[int] | None, Form(alias="c")] = None,
):
    if categories is None:
        categories = []

    api_update_indexer_categories(
        UpdateCategories(categories=categories),
        session,
        admin_user,
    )

    selected = set(categories)

    return catalog_response_toast(
        "Settings.Prowlarr.Category",
        "Categories updated",
        "success",
        indexer_categories=indexer_categories,
        selected_categories=selected,
    )


@router.put("/hx-indexers")
async def update_selected_indexers(
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
    indexer_ids: Annotated[list[int] | None, Form(alias="i")] = None,
):
    _ = admin_user
    if indexer_ids is None:
        indexer_ids = []
    prowlarr_config.set_indexers(session, indexer_ids)

    indexers = await get_indexers(session, client_session)
    selected_indexers = set(prowlarr_config.get_indexers(session))
    flush_prowlarr_cache()

    return catalog_response_toast(
        "Settings.Prowlarr.Indexer",
        "Indexers updated",
        "success",
        indexers=indexers,
        selected_indexers=selected_indexers,
    )
