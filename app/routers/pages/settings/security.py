from typing import Annotated

from aiohttp import ClientSession
from fastapi import APIRouter, Depends, Form, HTTPException, Response, Security
from sqlmodel import Session

from app.internal.auth.authentication import ABRAuth, DetailedUser
from app.internal.auth.config import auth_config
from app.internal.auth.login_types import LoginTypeEnum
from app.internal.auth.oidc_config import oidc_config
from app.internal.env_settings import Settings
from app.internal.models import GroupEnum
from app.routers.api.settings.security import (
    UpdateSecuritySettings,
)
from app.routers.api.settings.security import (
    reset_auth_secret as api_reset_auth_secret,
)
from app.routers.api.settings.security import (
    update_security_settings as api_update_security_settings,
)
from app.util.connection import get_connection
from app.util.db import get_session
from app.util.log import logger
from app.util.templates import catalog_response, catalog_response_toast
from app.util.toast import ToastException

router = APIRouter(prefix="/security")


@router.get("")
def read_security(
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    try:
        force_login_type = Settings().app.get_force_login_type()
    except ValueError as e:
        logger.error("Invalid force login type", exc_info=e)
        force_login_type = None

    return catalog_response(
        "Settings.Security.Index",
        user=admin_user,
        login_type=auth_config.get_login_type(session),
        access_token_expiry=auth_config.get_access_token_expiry_minutes(session),
        min_password_length=auth_config.get_min_password_length(session),
        oidc_endpoint=oidc_config.get(session, "oidc_endpoint", ""),
        oidc_client_secret=oidc_config.get(session, "oidc_client_secret", ""),
        oidc_client_id=oidc_config.get(session, "oidc_client_id", ""),
        oidc_scope=oidc_config.get(session, "oidc_scope", ""),
        oidc_username_claim=oidc_config.get(session, "oidc_username_claim", ""),
        oidc_group_claim=oidc_config.get(session, "oidc_group_claim", ""),
        oidc_redirect_scheme=oidc_config.get_redirect_scheme(session),
        oidc_logout_url=oidc_config.get(session, "oidc_logout_url", ""),
        force_login_type=force_login_type,
    )


@router.post("/hx-reset-auth")
def reset_auth_secret(
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    api_reset_auth_secret(session, admin_user)
    return Response(status_code=204, headers={"HX-Refresh": "true"})


@router.post("/hx-update")
async def update_security(
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
    login_type: Annotated[LoginTypeEnum | None, Form()] = None,
    access_token_expiry: Annotated[int | None, Form()] = None,
    min_password_length: Annotated[int | None, Form()] = None,
    oidc_endpoint: Annotated[str | None, Form()] = None,
    oidc_client_id: Annotated[str | None, Form()] = None,
    oidc_client_secret: Annotated[str | None, Form()] = None,
    oidc_scope: Annotated[str | None, Form()] = None,
    oidc_username_claim: Annotated[str | None, Form()] = None,
    oidc_group_claim: Annotated[str | None, Form()] = None,
    oidc_redirect_scheme: Annotated[str | None, Form()] = None,
    oidc_logout_url: Annotated[str | None, Form()] = None,
):
    try:
        force_login_type = Settings().app.get_force_login_type()
    except ValueError as e:
        logger.error("Invalid force login type", exc_info=e)
        raise ToastException("Invalid force login type configured", "error") from e

    if force_login_type is not None:
        login_type = force_login_type
    elif login_type is None:
        raise ToastException("Login type is required", "error")

    try:
        await api_update_security_settings(
            UpdateSecuritySettings(
                login_type=login_type,
                access_token_expiry=access_token_expiry,
                min_password_length=min_password_length,
                oidc_endpoint=oidc_endpoint,
                oidc_client_id=oidc_client_id,
                oidc_client_secret=oidc_client_secret,
                oidc_scope=oidc_scope,
                oidc_username_claim=oidc_username_claim,
                oidc_group_claim=oidc_group_claim,
                oidc_redirect_scheme=oidc_redirect_scheme,
                oidc_logout_url=oidc_logout_url,
            ),
            session,
            client_session,
            admin_user,
        )
    except HTTPException as e:
        raise ToastException(e.detail, "error") from None

    old = auth_config.get_login_type(session)

    return catalog_response_toast(
        "Settings.Security.Form",
        "Settings updated",
        "success",
        login_type=auth_config.get_login_type(session),
        access_token_expiry=auth_config.get_access_token_expiry_minutes(session),
        min_password_length=auth_config.get_min_password_length(session),
        oidc_endpoint=oidc_config.get(session, "oidc_endpoint", ""),
        oidc_client_secret=oidc_config.get(session, "oidc_client_secret", ""),
        oidc_client_id=oidc_config.get(session, "oidc_client_id", ""),
        oidc_scope=oidc_config.get(session, "oidc_scope", ""),
        oidc_username_claim=oidc_config.get(session, "oidc_username_claim", ""),
        oidc_group_claim=oidc_config.get(session, "oidc_group_claim", ""),
        oidc_redirect_scheme=oidc_config.get_redirect_scheme(session),
        oidc_logout_url=oidc_config.get(session, "oidc_logout_url", ""),
        force_login_type=force_login_type,
        headers={} if old == login_type else {"HX-Refresh": "true"},
    )
