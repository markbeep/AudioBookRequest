import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Security
from sqlmodel import Session

from app.internal.auth.authentication import ABRAuth, DetailedUser
from app.internal.models import ManualBookRequest
from app.internal.ranking.quality import quality_config
from app.routers.api.requests import (
    ManualRequest,
    create_manual_request,
    update_manual_request,
)
from app.util.db import get_session
from app.util.templates import catalog_response, catalog_response_toast

router = APIRouter(prefix="/manual")


@router.get("")
async def read_manual(
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(ABRAuth())],
    id: uuid.UUID | None = None,
):
    book = None
    if id:
        book = session.get(ManualBookRequest, id)

    auto_download = quality_config.get_auto_download(session)
    return catalog_response(
        "Manual.Index",
        user=user,
        book=book,
        auto_download=auto_download,
    )


@router.post("/hx-add")
async def add_manual(
    session: Annotated[Session, Depends(get_session)],
    background_task: BackgroundTasks,
    title: Annotated[str, Form()],
    author: Annotated[str, Form()],
    user: Annotated[DetailedUser, Security(ABRAuth())],
    narrator: Annotated[str | None, Form()] = None,
    subtitle: Annotated[str | None, Form()] = None,
    publish_date: Annotated[str | None, Form()] = None,
    info: Annotated[str | None, Form()] = None,
    id: uuid.UUID | None = None,
):
    req_body = ManualRequest(
        title=title,
        author=author,
        narrator=narrator,
        subtitle=subtitle,
        publish_date=publish_date,
        info=info,
    )
    if id:
        await update_manual_request(id, req_body, session, user)
    else:
        await create_manual_request(req_body, session, background_task, user)

    auto_download = quality_config.get_auto_download(session)

    return catalog_response_toast(
        "Manual.Form",
        "Successfully added request",
        "success",
        book=None,
        auto_download=auto_download,
    )
