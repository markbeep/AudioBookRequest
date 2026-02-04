import base64
import secrets
import time
from typing import Annotated, cast
from urllib.parse import urlencode, urljoin

import jwt
from aiohttp import ClientSession
from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Request,
    Response,
    Security,
    status,
)
from pydantic import BaseModel
from sqlmodel import Session, select

from app.internal.auth.authentication import (
    ABRAuth,
    DetailedUser,
    RequiresLoginException,
    authenticate_user,
    create_user,
    raise_for_invalid_password,
)
from app.internal.auth.config import auth_config
from app.internal.auth.login_types import LoginTypeEnum
from app.internal.auth.oidc_config import InvalidOIDCConfiguration, oidc_config
from app.internal.models import GroupEnum, User
from app.util.connection import USER_AGENT, get_connection
from app.util.db import get_session
from app.util.log import logger
from app.util.redirect import BaseUrlRedirectResponse, ClientRedirectResponse
from app.util.templates import templates

router = APIRouter(prefix="/auth", tags=["Auth"])


class _LoginTypeResponse(BaseModel):
    login_type: LoginTypeEnum


@router.get("/type", response_model=_LoginTypeResponse)
def get_login_type(
    session: Annotated[Session, Depends(get_session)],
):
    return _LoginTypeResponse(login_type=auth_config.get_login_type(session))


@router.get("/login")
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
        _ = await ABRAuth()(request, session)
        # already logged in
        return BaseUrlRedirectResponse(redirect_uri)
    except (HTTPException, RequiresLoginException):
        pass

    if login_type != LoginTypeEnum.oidc or backup:
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "hide_navbar": True,
                "redirect_uri": redirect_uri,
                "backup": backup,
            },
        )

    authorize_endpoint = oidc_config.get(session, "oidc_authorize_endpoint")
    client_id = oidc_config.get(session, "oidc_client_id")
    scope = oidc_config.get(session, "oidc_scope") or "openid"
    if not authorize_endpoint:
        raise InvalidOIDCConfiguration("Missing OIDC endpoint")
    if not client_id:
        raise InvalidOIDCConfiguration("Missing OIDC client ID")

    auth_redirect_uri = urljoin(str(request.url), "/auth/oidc")
    if oidc_config.get_redirect_https(session):
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


@router.post("/logout", response_model=ClientRedirectResponse)
async def logout(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    _: Annotated[DetailedUser, Security(ABRAuth())],
) -> ClientRedirectResponse:
    request.session["sub"] = ""
    login_type = auth_config.get_login_type(session)
    if login_type == LoginTypeEnum.oidc:
        logout_url = oidc_config.get(session, "oidc_logout_url")
        if logout_url:
            return ClientRedirectResponse(redirect=logout_url)
    return ClientRedirectResponse(redirect=None)


@router.post("/init")
def create_init(
    login_type: Annotated[LoginTypeEnum, Form()],
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    session: Annotated[Session, Depends(get_session)],
):
    if username.strip() == "":
        return HTTPException(
            status_code=400, detail="Username cannot be empty or whitespace only"
        )

    raise_for_invalid_password(session, password)

    user = create_user(username, password, GroupEnum.admin, root=True)
    session.add(user)
    auth_config.set_login_type(session, login_type)
    session.commit()

    return Response(status_code=201)


class _LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/token")
def login_access_token(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    body: _LoginRequest,
):
    user = authenticate_user(session, body.username, body.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

    # only admins can use the backup forms login
    login_type = auth_config.get_login_type(session)
    if login_type == LoginTypeEnum.oidc and not user.root:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not root user",
        )

    request.session["sub"] = body.username
    return Response(status_code=status.HTTP_200_OK)


class _AccessTokenBody(BaseModel):
    access_token: str | None = None
    expires_in: int | None = None


@router.get("/oidc")
async def login_oidc(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    code: str,
    state: str | None = None,
):
    token_endpoint = oidc_config.get(session, "oidc_token_endpoint")
    userinfo_endpoint = oidc_config.get(session, "oidc_userinfo_endpoint")
    client_id = oidc_config.get(session, "oidc_client_id")
    client_secret = oidc_config.get(session, "oidc_client_secret")
    username_claim = oidc_config.get(session, "oidc_username_claim")
    group_claim = oidc_config.get(session, "oidc_group_claim")

    if not token_endpoint:
        raise InvalidOIDCConfiguration("Missing OIDC endpoint")
    if not userinfo_endpoint:
        raise InvalidOIDCConfiguration("Missing OIDC userinfo endpoint")
    if not client_id:
        raise InvalidOIDCConfiguration("Missing OIDC client ID")
    if not client_secret:
        raise InvalidOIDCConfiguration("Missing OIDC client secret")
    if not username_claim:
        raise InvalidOIDCConfiguration("Missing OIDC username claim")

    auth_redirect_uri = urljoin(str(request.url), "/auth/oidc")
    if oidc_config.get_redirect_https(session):
        auth_redirect_uri = auth_redirect_uri.replace("http:", "https:")

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": auth_redirect_uri,
    }

    try:
        async with client_session.post(
            token_endpoint,
            data=data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": USER_AGENT,
            },
        ) as response:
            body = _AccessTokenBody.model_validate(await response.json())
    except Exception as e:
        logger.error("Failed to extract OIDC access token from body", error=str(e))
        raise InvalidOIDCConfiguration(
            "Failed to extract OIDC access token from body"
        ) from e

    if not body.access_token:
        return Response(status_code=status.HTTP_401_UNAUTHORIZED)

    async with client_session.get(
        userinfo_endpoint,
        headers={
            "Authorization": f"Bearer {body.access_token}",
            "User-Agent": USER_AGENT,
        },
    ) as response:
        userinfo = cast(object, await response.json())
        if not isinstance(userinfo, dict):
            logger.error(
                "Invalid OIDC userinfo response",
                userinfo_type=type(userinfo).__name__,
            )
            raise InvalidOIDCConfiguration("Invalid OIDC userinfo response")

    username = userinfo.get(username_claim)  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
    if not username or not isinstance(username, str):
        raise InvalidOIDCConfiguration("Missing valid string username claim")

    if group_claim:
        groups = cast(object, userinfo.get(group_claim, []))  # pyright: ignore[reportUnknownMemberType]
        if isinstance(groups, str):
            groups = groups.split(" ")
        if not isinstance(groups, list):
            logger.warning(
                "Invalid OIDC group claim type, expected list or string. Defaulted to empty groups list",
                group_claim_type=type(groups).__name__,
                username=username,
            )
            groups = []
        groups = [str(g) for g in groups if isinstance(g, str)]  # pyright: ignore[reportUnknownVariableType]
    else:
        groups = []

    user = session.exec(select(User).where(User.username == username)).first()
    if not user:
        user = create_user(
            username=username,
            # assign a random password to users created via OIDC
            password=base64.encodebytes(secrets.token_bytes(64)).decode("utf-8"),
        )

    # Don't overwrite the group if the user is root admin
    if not user.root:
        for group in groups:
            if group.lower() == "admin":
                user.group = GroupEnum.admin
                break
            elif group.lower() == "trusted":
                user.group = GroupEnum.trusted
                break
            elif group.lower() == "untrusted":
                user.group = GroupEnum.untrusted
                break

    session.add(user)
    session.commit()

    expires_in: int = (
        body.expires_in or auth_config.get_access_token_expiry_minutes(session) * 60
    )
    expires = int(time.time() + expires_in)

    request.session["sub"] = username
    request.session["exp"] = expires

    if state:
        decoded = cast(
            object,
            jwt.decode(
                state,
                auth_config.get_auth_secret(session),
                algorithms=["HS256"],
            ),
        )
        if (
            isinstance(decoded, dict)
            and "redirect_uri" in decoded
            and isinstance(decoded["redirect_uri"], str)
        ):
            redirect_uri = decoded["redirect_uri"]
        else:
            redirect_uri = "/"
    else:
        redirect_uri = "/"

    # We can't redirect server side, because that results in an infinite loop.
    # The session token is never correctly set causing any other endpoint to
    # redirect to the login page which in turn starts the OIDC flow again.
    # The redirect page allows for the cookie to properly be set on the browser
    # and then redirects client-side.
    return templates.TemplateResponse(
        "redirect.html",
        {
            "request": request,
            "hide_navbar": True,
            "redirect_uri": redirect_uri,
        },
    )


@router.get("/invalid-oidc")
def invalid_oidc(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    error: str | None = None,
):
    if auth_config.get_login_type(session) != LoginTypeEnum.oidc:
        return Response(status_code=status.HTTP_404_NOT_FOUND)
    return templates.TemplateResponse(
        "invalid_oidc.html",
        {
            "request": request,
            "error": error,
            "hide_navbar": True,
        },
        status_code=status.HTTP_200_OK,
    )
