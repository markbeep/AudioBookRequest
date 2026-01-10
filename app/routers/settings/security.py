from typing import Annotated, Optional

from aiohttp import ClientSession
from fastapi import APIRouter, Depends, Form, Request, Response, Security
from sqlmodel import Session

from app.internal.auth.authentication import ABRAuth, DetailedUser
from app.internal.auth.config import auth_config
from app.internal.auth.login_types import LoginTypeEnum
from app.internal.auth.oidc_config import InvalidOIDCConfiguration, oidc_config
from app.internal.env_settings import Settings
from app.internal.models import GroupEnum
from app.util.connection import get_connection
from app.util.db import get_session
from app.util.log import logger
from app.util.templates import template_response
from app.util.time import Minute
from app.util.toast import ToastException

router = APIRouter(prefix="/security")


@router.get("")
def read_security(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    try:
        force_login_type = Settings().app.get_force_login_type()
    except ValueError as e:
        logger.error("Invalid force login type", exc_info=e)
        force_login_type = None

    return template_response(
        "settings_page/security.html",
        request,
        admin_user,
        {
            "page": "security",
            "login_type": auth_config.get_login_type(session),
            "access_token_expiry": auth_config.get_access_token_expiry_minutes(session),
            "min_password_length": auth_config.get_min_password_length(session),
            "oidc_endpoint": oidc_config.get(session, "oidc_endpoint", ""),
            "oidc_client_secret": oidc_config.get(session, "oidc_client_secret", ""),
            "oidc_client_id": oidc_config.get(session, "oidc_client_id", ""),
            "oidc_scope": oidc_config.get(session, "oidc_scope", ""),
            "oidc_username_claim": oidc_config.get(session, "oidc_username_claim", ""),
            "oidc_group_claim": oidc_config.get(session, "oidc_group_claim", ""),
            "oidc_redirect_https": oidc_config.get_redirect_https(session),
            "oidc_logout_url": oidc_config.get(session, "oidc_logout_url", ""),
            "force_login_type": force_login_type,
        },
    )


@router.post("/reset-auth")
def reset_auth_secret(
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    _ = admin_user
    auth_config.reset_auth_secret(session)
    return Response(status_code=204, headers={"HX-Refresh": "true"})


@router.post("")
async def update_security(
    login_type: Annotated[LoginTypeEnum, Form()],
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
    access_token_expiry: Annotated[Optional[int], Form()] = None,
    min_password_length: Annotated[Optional[int], Form()] = None,
    oidc_endpoint: Annotated[Optional[str], Form()] = None,
    oidc_client_id: Annotated[Optional[str], Form()] = None,
    oidc_client_secret: Annotated[Optional[str], Form()] = None,
    oidc_scope: Annotated[Optional[str], Form()] = None,
    oidc_username_claim: Annotated[Optional[str], Form()] = None,
    oidc_group_claim: Annotated[Optional[str], Form()] = None,
    oidc_redirect_https: Annotated[Optional[bool], Form()] = None,
    oidc_logout_url: Annotated[Optional[str], Form()] = None,
):
    if (
        login_type in [LoginTypeEnum.basic, LoginTypeEnum.forms]
        and min_password_length is not None
    ):
        if min_password_length < 1:
            raise ToastException(
                "Minimum password length can't be 0 or negative", "error"
            )
        else:
            auth_config.set_min_password_length(session, min_password_length)

    if access_token_expiry is not None:
        if access_token_expiry < 1:
            raise ToastException("Access token expiry can't be 0 or negative", "error")
        else:
            auth_config.set_access_token_expiry_minutes(
                session, Minute(access_token_expiry)
            )

    if login_type == LoginTypeEnum.oidc:
        if oidc_endpoint:
            try:
                await oidc_config.set_endpoint(session, client_session, oidc_endpoint)
            except InvalidOIDCConfiguration as e:
                raise ToastException(f"Invalid OIDC endpoint: {e.detail}", "error")
        if oidc_client_id:
            oidc_config.set(session, "oidc_client_id", oidc_client_id)
        if oidc_client_secret:
            oidc_config.set(session, "oidc_client_secret", oidc_client_secret)
        if oidc_scope:
            oidc_config.set(session, "oidc_scope", oidc_scope)
        if oidc_username_claim:
            oidc_config.set(session, "oidc_username_claim", oidc_username_claim)
        if oidc_redirect_https:
            oidc_config.set(
                session,
                "oidc_redirect_https",
                "true" if oidc_redirect_https else "",
            )
        if oidc_logout_url:
            oidc_config.set(session, "oidc_logout_url", oidc_logout_url)
        if oidc_group_claim is not None:
            oidc_config.set(session, "oidc_group_claim", oidc_group_claim)

        error_message = await oidc_config.validate(session, client_session)
        if error_message:
            raise ToastException(error_message, "error")

    try:
        force_login_type = Settings().app.get_force_login_type()
    except ValueError as e:
        logger.error("Invalid force login type", exc_info=e)
        force_login_type = None
    if force_login_type and login_type != force_login_type:
        raise ToastException(
            f"Cannot change login type to '{login_type.value}' when force login type is set to '{force_login_type.value}'",
            "error",
        )

    old = auth_config.get_login_type(session)
    auth_config.set_login_type(session, login_type)

    return template_response(
        "settings_page/security.html",
        request,
        admin_user,
        {
            "page": "security",
            "login_type": auth_config.get_login_type(session),
            "access_token_expiry": auth_config.get_access_token_expiry_minutes(session),
            "oidc_client_id": oidc_config.get(session, "oidc_client_id", ""),
            "oidc_scope": oidc_config.get(session, "oidc_scope", ""),
            "oidc_username_claim": oidc_config.get(session, "oidc_username_claim", ""),
            "oidc_group_claim": oidc_config.get(session, "oidc_group_claim", ""),
            "oidc_client_secret": oidc_config.get(session, "oidc_client_secret", ""),
            "oidc_endpoint": oidc_config.get(session, "oidc_endpoint", ""),
            "oidc_redirect_https": oidc_config.get_redirect_https(session),
            "oidc_logout_url": oidc_config.get(session, "oidc_logout_url", ""),
            "force_login_type": force_login_type,
            "success": "Settings updated",
        },
        block_name="form",
        headers={} if old == login_type else {"HX-Refresh": "true"},
    )
