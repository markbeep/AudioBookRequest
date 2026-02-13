from typing import Annotated

from aiohttp import ClientSession
from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Security
from sqlmodel import Session

from app.internal.audible.types import audible_region_type, get_region_tld_from_settings
from app.internal.auth.authentication import ABRAuth, DetailedUser
from app.internal.ranking.quality import quality_config
from app.routers.api.requests import create_request
from app.util.censor import censor
from app.util.connection import get_connection
from app.util.db import get_session
from app.util.log import logger
from app.util.templates import catalog_response
from app.util.toast import ToastException

router = APIRouter(prefix="/request")


@router.post("/hx-add/{asin}")
async def add_request(
    asin: str,
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    background_task: BackgroundTasks,
    user: Annotated[DetailedUser, Security(ABRAuth())],
    region: Annotated[audible_region_type | None, Form()] = None,
):
    try:
        book = await create_request(
            asin=asin,
            session=session,
            client_session=client_session,
            background_task=background_task,
            user=user,
            region=region,
        )
    except HTTPException as e:
        logger.warning(
            e.detail,
            username=censor(user.username),
            asin=asin,
        )
        raise ToastException(e.detail) from e

    return catalog_response(
        "BookCard",
        book_with_requests=book,
        auto_start_download=quality_config.get_auto_download(session),
        region_tld=get_region_tld_from_settings(),
        user=user,
    )
