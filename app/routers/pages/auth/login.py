from typing import Annotated
from urllib.parse import urlencode

import jwt
from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session

from app.internal.auth.authentication import (
    ABRAuth,
    RequiresLoginException,
    authenticate_user,
)
from app.internal.auth.config import auth_config
from app.internal.auth.login_types import LoginTypeEnum
from app.internal.auth.oidc_config import InvalidOIDCConfiguration, oidc_config
from app.util.db import get_session
from app.util.log import logger
from app.util.redirect import BaseUrlRedirectResponse
from app.util.templates import catalog_response
from app.util.toast import ToastException

router = APIRouter(prefix="/login")


@router.get("")
async def login(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    redirect_uri: str = "/",
    backup: bool = False,
):
    login_type = auth_config.get(session, "login_type")
    if login_type in [LoginTypeEnum.basic, LoginTypeEnum.none]:
        return BaseUrlRedirectResponse(redirect_uri)
    if login_type != LoginTypeEnum.oidc and backup:
        backup = False

    try:
        await ABRAuth()(request, session)
        # already logged in
        return BaseUrlRedirectResponse(redirect_uri)
    except HTTPException, RequiresLoginException:
        pass

    if login_type == LoginTypeEnum.forms or backup:
        title = "Backup Login" if backup else "Login"
        return catalog_response(
            "Auth.Login",
            title=title,
            backup=backup,
            redirect_uri=redirect_uri,
        )

    authorize_endpoint = oidc_config.get(session, "oidc_authorize_endpoint")
    client_id = oidc_config.get(session, "oidc_client_id")
    scope = oidc_config.get(session, "oidc_scope") or "openid"
    if not authorize_endpoint:
        raise InvalidOIDCConfiguration("Missing OIDC endpoint")
    if not client_id:
        raise InvalidOIDCConfiguration("Missing OIDC client ID")

    auth_redirect_uri = str(request.url_for("login_oidc"))
    scheme = oidc_config.get_redirect_scheme(session)
    if scheme == "http":
        auth_redirect_uri = auth_redirect_uri.replace("https:", "http:")
    elif scheme == "https":
        auth_redirect_uri = auth_redirect_uri.replace("http:", "https:")

    logger.info(
        "Redirecting to OIDC login",
        authorize_endpoint=authorize_endpoint,
        redirect_uri=auth_redirect_uri,
    )

    state = jwt.encode(
        {"redirect_uri": redirect_uri},
        auth_config.get_auth_secret(session),
        algorithm="HS256",
    )

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": auth_redirect_uri,
        "scope": scope,
        "state": state,
    }
    return BaseUrlRedirectResponse(f"{authorize_endpoint}?" + urlencode(params))


@router.post("/hx-login")
def login_access_token(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    redirect_uri: Annotated[str, Form()] = "/",
):
    user = authenticate_user(session, form_data.username, form_data.password)
    if not user:
        raise ToastException("Invalid login", "error")

    # only admins can use the backup forms login
    login_type = auth_config.get_login_type(session)
    if login_type == LoginTypeEnum.oidc and not user.root:
        raise ToastException("Not root admin", "error")

    request.session["sub"] = form_data.username

    # enforce a refresh and redirect on the client side
    return Response(
        status_code=status.HTTP_200_OK,
        headers={"HX-Redirect": redirect_uri},
    )
