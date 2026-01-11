import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Security
from sqlmodel import Session, select

from app.internal.auth.authentication import ABRAuth, DetailedUser
from app.internal.models import (
    APIKey,
)
from app.routers.api.settings.account import (
    ChangePasswordRequest,
    CreateAPIKeyRequest,
)
from app.routers.api.settings.account import change_password as api_change_password
from app.routers.api.settings.account import (
    create_new_api_key as api_create_new_api_key,
)
from app.routers.api.settings.account import delete_api_key as api_delete_api_key
from app.routers.api.settings.account import toggle_api_key as api_toggle_api_key
from app.util.db import get_session
from app.util.templates import template_response
from app.util.toast import ToastException

router = APIRouter(prefix="/account")


@router.get("")
def read_account(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(ABRAuth())],
):
    api_keys = session.exec(
        select(APIKey).where(APIKey.user_username == user.username)
    ).all()
    return template_response(
        "settings_page/account.html",
        request,
        user,
        {"page": "account", "api_keys": api_keys},
    )


@router.post("/password")
def change_password(
    request: Request,
    old_password: Annotated[str, Form()],
    password: Annotated[str, Form()],
    confirm_password: Annotated[str, Form()],
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(ABRAuth())],
):
    try:
        api_change_password(
            ChangePasswordRequest(
                old_password=old_password,
                new_password=password,
                confirm_password=confirm_password,
            ),
            session,
            user,
        )
    except HTTPException as e:
        raise ToastException(e.detail, "error")

    return template_response(
        "settings_page/account.html",
        request,
        user,
        {"page": "account", "success": "Password changed"},
        block_name="change_password",
    )


@router.post("/api-key")
def create_new_api_key(
    request: Request,
    name: Annotated[str, Form()],
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(ABRAuth())],
):
    if not name.strip():
        raise ToastException("API key name cannot be empty", "error")

    try:
        resp = api_create_new_api_key(CreateAPIKeyRequest(name=name), session, user)
        private_key = resp.key
    except HTTPException as e:
        raise ToastException(e.detail, "error")

    api_keys = session.exec(
        select(APIKey).where(APIKey.user_username == user.username)
    ).all()

    return template_response(
        "settings_page/account.html",
        request,
        user,
        {
            "page": "account",
            "api_keys": api_keys,
            "success": f"API key created: {private_key}",
            "show_api_key": True,
            "new_api_key": private_key,
        },
        block_name="api_keys",
    )


@router.delete("/api-key/{api_key_id}")
def delete_api_key(
    request: Request,
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
    return template_response(
        "settings_page/account.html",
        request,
        user,
        {
            "page": "account",
            "api_keys": api_keys,
            "success": "API key deleted",
        },
        block_name="api_keys",
    )


@router.patch("/api-key/{api_key_id}/toggle")
def toggle_api_key(
    request: Request,
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

    return template_response(
        "settings_page/account.html",
        request,
        user,
        {
            "page": "account",
            "api_keys": api_keys,
            "success": f"API key {'enabled' if enabled else 'disabled'}",
        },
        block_name="api_keys",
    )
