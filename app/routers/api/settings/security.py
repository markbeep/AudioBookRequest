from typing import Annotated, Optional

from aiohttp import ClientSession
from fastapi import APIRouter, Depends, HTTPException, Response, Security
from pydantic import BaseModel
from sqlmodel import Session

from app.internal.auth.authentication import AnyAuth, DetailedUser
from app.internal.auth.config import auth_config
from app.internal.auth.login_types import LoginTypeEnum
from app.internal.auth.oidc_config import InvalidOIDCConfiguration, oidc_config
from app.internal.env_settings import Settings
from app.internal.models import GroupEnum
from app.util.connection import get_connection
from app.util.db import get_session
from app.util.log import logger
from app.util.time import Minute

router = APIRouter(prefix="/security")


class SecuritySettings(BaseModel):
    login_type: LoginTypeEnum
    access_token_expiry: int
    min_password_length: int
    oidc_endpoint: str
    oidc_client_secret: str
    oidc_client_id: str
    oidc_scope: str
    oidc_username_claim: str
    oidc_group_claim: str
    oidc_redirect_scheme: str
    oidc_logout_url: str
    force_login_type: LoginTypeEnum | None


@router.get("", response_model=SecuritySettings)
def get_security_settings(
    session: Annotated[Session, Depends(get_session)],
    _: Annotated[DetailedUser, Security(AnyAuth(GroupEnum.admin))],
):
    try:
        force_login_type = Settings().app.get_force_login_type()
    except ValueError as e:
        logger.error("Invalid force login type", exc_info=e)
        force_login_type = None

    return SecuritySettings(
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


@router.post("/reset-auth", status_code=204)
def reset_auth_secret(
    session: Annotated[Session, Depends(get_session)],
    _: Annotated[DetailedUser, Security(AnyAuth(GroupEnum.admin))],
):
    auth_config.reset_auth_secret(session)
    return Response(status_code=204)


class UpdateSecuritySettings(BaseModel):
    login_type: LoginTypeEnum
    access_token_expiry: Optional[int] = None
    min_password_length: Optional[int] = None
    oidc_endpoint: Optional[str] = None
    oidc_client_id: Optional[str] = None
    oidc_client_secret: Optional[str] = None
    oidc_scope: Optional[str] = None
    oidc_username_claim: Optional[str] = None
    oidc_group_claim: Optional[str] = None
    oidc_redirect_scheme: Optional[str] = None
    oidc_logout_url: Optional[str] = None


@router.patch("", status_code=204)
async def update_security_settings(
    body: UpdateSecuritySettings,
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    _: Annotated[DetailedUser, Security(AnyAuth(GroupEnum.admin))],
):
    if (
        body.login_type in [LoginTypeEnum.basic, LoginTypeEnum.forms]
        and body.min_password_length is not None
    ):
        if body.min_password_length < 1:
            raise HTTPException(
                status_code=400, detail="Minimum password length can't be 0 or negative"
            )
        else:
            auth_config.set_min_password_length(session, body.min_password_length)

    if body.access_token_expiry is not None:
        if body.access_token_expiry < 1:
            raise HTTPException(
                status_code=400, detail="Access token expiry can't be 0 or negative"
            )
        else:
            auth_config.set_access_token_expiry_minutes(
                session, Minute(body.access_token_expiry)
            )

    if body.login_type == LoginTypeEnum.oidc:
        if body.oidc_endpoint:
            try:
                await oidc_config.set_endpoint(
                    session, client_session, body.oidc_endpoint
                )
            except InvalidOIDCConfiguration as e:
                raise HTTPException(
                    status_code=400, detail=f"Invalid OIDC endpoint: {e.detail}"
                )
        if body.oidc_client_id:
            oidc_config.set(session, "oidc_client_id", body.oidc_client_id)
        if body.oidc_client_secret:
            oidc_config.set(session, "oidc_client_secret", body.oidc_client_secret)
        if body.oidc_scope:
            oidc_config.set(session, "oidc_scope", body.oidc_scope)
        if body.oidc_username_claim:
            oidc_config.set(session, "oidc_username_claim", body.oidc_username_claim)
        if body.oidc_redirect_scheme is not None:
            scheme = body.oidc_redirect_scheme
            value = scheme if scheme in ("http", "https") else "auto"
            oidc_config.set(session, "oidc_redirect_scheme", value)
        if body.oidc_logout_url:
            oidc_config.set(session, "oidc_logout_url", body.oidc_logout_url)
        if body.oidc_group_claim is not None:
            oidc_config.set(session, "oidc_group_claim", body.oidc_group_claim)

        error_message = await oidc_config.validate(session, client_session)
        if error_message:
            raise HTTPException(status_code=400, detail=error_message)

    try:
        force_login_type = Settings().app.get_force_login_type()
    except ValueError as e:
        logger.error("Invalid force login type", exc_info=e)
        force_login_type = None
    if force_login_type and body.login_type != force_login_type:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot change login type to '{body.login_type.value}' when force login type is set to '{force_login_type.value}'",
        )

    auth_config.set_login_type(session, body.login_type)

    return Response(status_code=204)
