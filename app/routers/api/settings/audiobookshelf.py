from typing import Annotated

from aiohttp import ClientSession
from fastapi import APIRouter, Depends, Form, HTTPException, Response, Security
from pydantic import BaseModel
from sqlmodel import Session

from app.internal.audiobookshelf.client import (
    abs_get_libraries,
    abs_list_library_items,
    abs_trigger_scan,
)
from app.internal.audiobookshelf.config import abs_config
from app.internal.audiobookshelf.types import ABSLibrary
from app.internal.auth.authentication import AnyAuth, DetailedUser
from app.internal.models import GroupEnum
from app.util.connection import get_connection
from app.util.db import get_session
from app.util.log import logger

router = APIRouter(prefix="/audiobookshelf")


class ABSResponse(BaseModel):
    abs_base_url: str
    abs_api_token: str
    abs_library_id: str
    abs_check_downloaded: bool
    abs_libraries: list[ABSLibrary]


@router.get("")
async def read_abs(
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    admin_user: Annotated[DetailedUser, Security(AnyAuth(GroupEnum.admin))],
):
    _ = admin_user
    base_url = abs_config.get_base_url(session) or ""
    api_token = abs_config.get_api_token(session) or ""
    library_id = abs_config.get_library_id(session) or ""
    check_downloaded = abs_config.get_check_downloaded(session)
    libraries = []
    if base_url and api_token:
        libraries = await abs_get_libraries(session, client_session)

    return ABSResponse(
        abs_base_url=base_url,
        abs_api_token=api_token,
        abs_library_id=library_id,
        abs_check_downloaded=check_downloaded,
        abs_libraries=libraries,
    )


@router.put("/base-url")
def update_abs_base_url(
    base_url: Annotated[str, Form()],
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(AnyAuth(GroupEnum.admin))],
):
    _ = admin_user
    abs_config.set_base_url(session, base_url)
    return Response(status_code=204)


@router.put("/api-token")
def update_abs_api_token(
    api_token: Annotated[str, Form(alias="api_token")],
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(AnyAuth(GroupEnum.admin))],
):
    _ = admin_user
    abs_config.set_api_token(session, api_token)
    return Response(status_code=204)


@router.put("/library")
def update_abs_library(
    library_id: Annotated[str, Form(alias="library_id")],
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(AnyAuth(GroupEnum.admin))],
):
    _ = admin_user
    abs_config.set_library_id(session, library_id)
    return Response(status_code=204)


@router.put("/check-downloaded")
def update_abs_check_downloaded(
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(AnyAuth(GroupEnum.admin))],
    check_downloaded: Annotated[bool, Form()] = False,
):
    _ = admin_user
    abs_config.set_check_downloaded(session, check_downloaded)
    return Response(status_code=204)


class TestResponse(BaseModel):
    library_count: int
    triggered_scan: bool
    sample_items: list[str]


@router.get("/test-connection")
async def test_abs_connection(
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    _: Annotated[DetailedUser, Security(AnyAuth(GroupEnum.admin))],
):
    abs_config.raise_if_invalid(session)
    libraries = await abs_get_libraries(session, client_session)
    if not libraries:
        raise HTTPException(
            status_code=400, detail="Failed to connect to Audiobookshelf"
        )
    logger.info(
        "Successfully connected to Audiobookshelf", library_count=len(libraries)
    )
    success = await abs_trigger_scan(session, client_session)
    if not success:
        raise HTTPException(
            status_code=400, detail="Failed to trigger scan on Audiobookshelf"
        )
    logger.info("Successfully triggered scan on Audiobookshelf")
    list_library_items = await abs_list_library_items(session, client_session)
    logger.info(
        "Fetched items from Audiobookshelf library",
        item_count=len(list_library_items),
    )
    return TestResponse(
        library_count=len(libraries),
        triggered_scan=success,
        sample_items=[item.title for item in list_library_items[:5]],
    )
