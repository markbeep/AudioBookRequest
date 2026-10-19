from typing import Annotated

from fastapi import APIRouter, Depends, Form, Response, Security
from sqlmodel import Session

from app.internal.auth.authentication import ABRAuth, DetailedUser
from app.internal.models import GroupEnum
from app.routers.api.settings.chaptarr import (
    UpdateApiKey,
    UpdateBaseUrl,
)
from app.routers.api.settings.chaptarr import (
    update_chaptarr_api_key as api_update_chaptarr_api_key,
)
from app.routers.api.settings.chaptarr import (
    update_chaptarr_base_url as api_update_chaptarr_base_url,
)
from app.util.db import get_session

router = APIRouter(prefix="/chaptarr")


@router.put("/hx-base-url")
def update_chaptarr_base_url(
    base_url: Annotated[str, Form()],
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    api_update_chaptarr_base_url(UpdateBaseUrl(base_url=base_url), session, admin_user)
    return Response(status_code=204, headers={"HX-Refresh": "true"})


@router.put("/hx-api-key")
def update_chaptarr_api_key(
    api_key: Annotated[str, Form()],
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    api_update_chaptarr_api_key(UpdateApiKey(api_key=api_key), session, admin_user)
    return Response(status_code=204, headers={"HX-Refresh": "true"})
