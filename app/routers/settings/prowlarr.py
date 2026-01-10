from typing import Annotated

from aiohttp import ClientSession
from fastapi import APIRouter, Depends, Form, Request, Response, Security
from sqlmodel import Session

from app.internal.auth.authentication import ABRAuth, DetailedUser
from app.internal.models import GroupEnum
from app.internal.prowlarr.indexer_categories import indexer_categories
from app.internal.prowlarr.prowlarr import (
    flush_prowlarr_cache,
    get_indexers,
    prowlarr_config,
)
from app.util.connection import get_connection
from app.util.db import get_session
from app.util.templates import template_response

router = APIRouter(prefix="/prowlarr")


@router.get("")
async def read_prowlarr(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
    prowlarr_misconfigured: object | None = None,
):
    prowlarr_base_url = prowlarr_config.get_base_url(session)
    prowlarr_api_key = prowlarr_config.get_api_key(session)
    selected = set(prowlarr_config.get_categories(session))
    indexers = await get_indexers(session, client_session)
    selected_indexers = set(prowlarr_config.get_indexers(session))

    return template_response(
        "settings_page/prowlarr.html",
        request,
        admin_user,
        {
            "page": "prowlarr",
            "prowlarr_base_url": prowlarr_base_url or "",
            "prowlarr_api_key": prowlarr_api_key,
            "indexer_categories": indexer_categories,
            "selected_categories": selected,
            "indexers": indexers,
            "selected_indexers": selected_indexers,
            "prowlarr_misconfigured": True if prowlarr_misconfigured else False,
        },
    )


@router.put("/api-key")
def update_prowlarr_api_key(
    api_key: Annotated[str, Form()],
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    _ = admin_user
    prowlarr_config.set_api_key(session, api_key)
    flush_prowlarr_cache()
    return Response(status_code=204, headers={"HX-Refresh": "true"})


@router.put("/base-url")
def update_prowlarr_base_url(
    base_url: Annotated[str, Form()],
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    _ = admin_user
    prowlarr_config.set_base_url(session, base_url)
    flush_prowlarr_cache()
    return Response(status_code=204, headers={"HX-Refresh": "true"})


@router.put("/category")
def update_indexer_categories(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
    categories: Annotated[list[int] | None, Form(alias="c")] = None,
):
    if categories is None:
        categories = []
    prowlarr_config.set_categories(session, categories)
    selected = set(categories)
    flush_prowlarr_cache()

    return template_response(
        "settings_page/prowlarr.html",
        request,
        admin_user,
        {
            "indexer_categories": indexer_categories,
            "selected_categories": selected,
            "success": "Categories updated",
        },
        block_name="category",
    )


@router.put("/indexers")
async def update_selected_indexers(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
    indexer_ids: Annotated[list[int] | None, Form(alias="i")] = None,
):
    if indexer_ids is None:
        indexer_ids = []
    prowlarr_config.set_indexers(session, indexer_ids)

    indexers = await get_indexers(session, client_session)
    selected_indexers = set(prowlarr_config.get_indexers(session))
    flush_prowlarr_cache()

    return template_response(
        "settings_page/prowlarr.html",
        request,
        admin_user,
        {
            "indexers": indexers,
            "selected_indexers": selected_indexers,
            "success": "Indexers updated",
        },
        block_name="indexer",
    )
