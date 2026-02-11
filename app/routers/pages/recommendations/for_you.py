from typing import Annotated

from aiohttp import ClientSession
from fastapi import APIRouter, Depends, Security
from sqlmodel import Session

from app.internal.audible.types import get_region_tld_from_settings
from app.internal.auth.authentication import ABRAuth, DetailedUser
from app.internal.ranking.quality import quality_config
from app.routers.api.recommendations import (
    get_user_recommendations as api_get_user_recommendations,
)
from app.util.connection import get_connection
from app.util.db import get_session
from app.util.templates import catalog_response

router = APIRouter(prefix="/for-you")


@router.get("")
async def get_for_you_recommendations(
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    user: Annotated[DetailedUser, Security(ABRAuth())],
    page: int = 1,
    per_page: int = 10,
):
    result = await api_get_user_recommendations(
        session=session,
        client_session=client_session,
        user=user,
        limit=per_page,
        offset=(page - 1) * per_page,
    )
    has_next = result.total > page * per_page

    return catalog_response(
        "Recommendations.ForYou",
        user=user,
        recommendations=result.recommendations,
        page=page,
        per_page=per_page,
        has_next=has_next,
        total_items=result.total,
        region_tld=get_region_tld_from_settings(),
        auto_start_download=quality_config.get_auto_download(session),
    )
