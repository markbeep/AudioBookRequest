from typing import Annotated

from aiohttp import ClientSession
from fastapi import APIRouter, Depends, Query, Security
from sqlmodel import Session

from app.internal.audible.types import (
    audible_region_type,
    audible_regions,
    get_region_from_settings,
)
from app.internal.auth.authentication import ABRAuth, DetailedUser
from app.internal.models import GroupEnum
from app.internal.prowlarr.util import prowlarr_config
from app.internal.ranking.quality import quality_config
from app.routers.api.search import search_books
from app.routers.api.search import search_suggestions as api_search_suggestions
from app.util.connection import get_connection
from app.util.db import get_session
from app.util.log import logger
from app.util.templates import catalog_response
from app.util.toast import ToastException

from . import manual

router = APIRouter(prefix="/search")

router.include_router(manual.router)


@router.get("")
async def read_search(
    client_session: Annotated[ClientSession, Depends(get_connection)],
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(ABRAuth())],
    query: Annotated[str | None, Query(alias="q")] = None,
    num_results: int = 20,
    page: int = 0,
    region: audible_region_type | None = None,
):
    if region is None:
        region = get_region_from_settings()
    try:
        results = await search_books(
            client_session=client_session,
            user=user,
            query=query,
            num_results=num_results,
            page=page,
            region=region,
        )

        prowlarr_configured = prowlarr_config.is_valid(session)

        return catalog_response(
            "Search.Index",
            user=user,
            search_term=query or "",
            search_results=results,
            regions=audible_regions,
            selected_region=region,
            page=page,
            auto_start_download=quality_config.get_auto_download(session)
            and user.is_above(GroupEnum.trusted),
            prowlarr_configured=prowlarr_configured,
        )

    except Exception as e:
        session.rollback()
        logger.exception("Error during search", error=e)
        raise ToastException(
            "An error occurred while searching for books. Please try again later."
        ) from e


@router.get("/hx-suggestions")
async def search_suggestions(
    query: Annotated[str, Query(alias="q")],
    user: Annotated[DetailedUser, Security(ABRAuth())],
    region: audible_region_type | None = None,
):
    if query.strip():
        suggestions = await api_search_suggestions(query, user, region)
    else:
        suggestions = []
    return catalog_response(
        "Search.Suggestions",
        id="search-suggestions",
        suggestions=suggestions,
    )
