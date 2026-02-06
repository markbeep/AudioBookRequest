import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Security
from sqlmodel import Session, select

from app.internal.auth.authentication import ABRAuth, DetailedUser
from app.internal.auth.config import auth_config
from app.internal.auth.login_types import LoginTypeEnum
from app.internal.models import APIKey
from app.routers.api.settings.account import ChangePasswordRequest, CreateAPIKeyRequest
from app.routers.api.settings.account import change_password as api_change_password
from app.routers.api.settings.account import (
    create_new_api_key as api_create_new_api_key,
)
from app.routers.api.settings.account import delete_api_key as api_delete_api_key
from app.routers.api.settings.account import toggle_api_key as api_toggle_api_key
from app.util.db import get_session
from app.util.templates import catalog_response, catalog_response_toast
from app.util.toast import ToastException

router = APIRouter(prefix="/account")


@router.get("")
def read_account(
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(ABRAuth())],
):
    api_keys = session.exec(
        select(APIKey).where(APIKey.user_username == user.username)
    ).all()
    login_type = auth_config.get_login_type(session)
    if login_type == LoginTypeEnum.forms or login_type == LoginTypeEnum.basic:
        allow_password_change = True
    else:
        allow_password_change = False
    return catalog_response(
        "Settings.Account.Index",
        user=user,
        api_keys=api_keys,
        allow_password_change=allow_password_change,
    )


@router.post("/hx-password")
def change_password(
    old_password: Annotated[str, Form()],
    password: Annotated[str, Form()],
    confirm_password: Annotated[str, Form()],
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(ABRAuth())],
):
    login_type = auth_config.get_login_type(session)
    if not (login_type == LoginTypeEnum.forms or login_type == LoginTypeEnum.basic):
        raise HTTPException(400, "Password change not allowed for current login type")

    api_change_password(
        ChangePasswordRequest(
            old_password=old_password,
            new_password=password,
            confirm_password=confirm_password,
        ),
        session,
        user,
    )

    return catalog_response_toast(
        "Settings.Account.ChangePassword",
        "Password changed",
        "success",
    )


@router.post("/hx-api-key")
def create_new_api_key(
    name: Annotated[str, Form()],
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(ABRAuth())],
):
    if not name.strip():
        raise ToastException("API key name cannot be empty", "error")

    resp = api_create_new_api_key(CreateAPIKeyRequest(name=name), session, user)
    private_key = resp.key

    api_keys = session.exec(
        select(APIKey).where(APIKey.user_username == user.username)
    ).all()

    return catalog_response_toast(
        "Settings.Account.APIKeys",
        f"API key created: {name}",
        "success",
        api_keys=api_keys,
        show_api_key=True,
        new_api_key=private_key,
    )


@router.delete("/hx-api-key/{api_key_id}")
def delete_api_key(
    api_key_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(ABRAuth())],
):
    try:
        api_delete_api_key(str(api_key_id), session, user)
    except HTTPException as e:
        raise ToastException(e.detail, "error")

    api_keys = session.exec(
        select(APIKey).where(APIKey.user_username == user.username)
    ).all()

    return catalog_response_toast(
        "Settings.Account.APIKeys",
        "API key deleted",
        "success",
        api_keys=api_keys,
    )


@router.patch("/hx-api-key/{api_key_id}/toggle")
def toggle_api_key(
    api_key_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(ABRAuth())],
):
    try:
        api_toggle_api_key(str(api_key_id), session, user)
    except HTTPException as e:
        raise ToastException(e.detail, "error")

    api_keys = session.exec(
        select(APIKey).where(APIKey.user_username == user.username)
    ).all()
    enabled = next((k.enabled for k in api_keys if k.id == api_key_id), False)

    return catalog_response_toast(
        "Settings.Account.APIKeys",
        f"API key {'enabled' if enabled else 'disabled'}",
        "success",
        api_keys=api_keys,
    )
