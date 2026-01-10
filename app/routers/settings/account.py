import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Security
from sqlmodel import Session, select

from app.internal.auth.authentication import (
    ABRAuth,
    DetailedUser,
    create_api_key,
    create_user,
    is_correct_password,
    raise_for_invalid_password,
)
from app.internal.models import (
    APIKey,
    User,
)
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
    if not is_correct_password(user, old_password):
        raise ToastException("Old password is incorrect", "error")
    try:
        raise_for_invalid_password(session, password, confirm_password)
    except HTTPException as e:
        raise ToastException(e.detail, "error")

    new_user = create_user(user.username, password, user.group)
    old_user = session.exec(select(User).where(User.username == user.username)).one()
    old_user.password = new_user.password
    session.add(old_user)
    session.commit()

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

    api_key, private_key = create_api_key(user, name.strip())

    same_name_key = session.exec(
        select(APIKey).where(
            APIKey.user_username == user.username, APIKey.name == name.strip()
        )
    ).first()
    if same_name_key:
        raise ToastException("API key name must be unique", "error")

    session.add(api_key)
    session.commit()

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
    api_key = session.exec(
        select(APIKey).where(
            APIKey.id == api_key_id, APIKey.user_username == user.username
        )
    ).first()

    if not api_key:
        raise ToastException("API key not found", "error", cause_refresh=True)

    session.delete(api_key)
    session.commit()

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
    api_key = session.exec(
        select(APIKey).where(
            APIKey.id == api_key_id,
            APIKey.user_username == user.username,
        )
    ).first()

    if not api_key:
        raise ToastException("API key not found", "error")

    api_key.enabled = not api_key.enabled
    session.add(api_key)
    session.commit()

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
            "success": f"API key {'enabled' if api_key.enabled else 'disabled'}",
        },
        block_name="api_keys",
    )
