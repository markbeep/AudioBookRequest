import base64
import os
import secrets
import time
import uuid
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
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlmodel import Session, select

from app.internal.auth.authentication import (
    ABRAuth,
    DetailedUser,
    RequiresLoginException,
    authenticate_user,
    create_user,
)
from app.internal.auth.config import auth_config
from app.internal.auth.login_types import LoginTypeEnum
from app.internal.auth.oidc_config import InvalidOIDCConfiguration, oidc_config
from app.internal.models import GroupEnum, User
from app.util.connection import USER_AGENT, get_connection
from app.util.db import get_session
from app.util.log import logger
from app.util.redirect import BaseUrlRedirectResponse
from app.util.templates import templates
from app.util.toast import ToastException

router = APIRouter(prefix="/auth")


def _validate_proxy_headers(request: Request) -> None:
    """
    Validate that proxy headers come from trusted IPs.

    Raises HTTPException(403) if proxy headers are present but were not trusted
    by Uvicorn (indicating a misconfigured FORWARDED_ALLOW_IPS).

    This prevents silent security degradation while keeping server config private.
    Basic rejection is logged at INFO level; detailed debugging info at DEBUG level.
    """
    x_forwarded_proto = request.headers.get("X-Forwarded-Proto")

    # No proxy headers present - direct access is fine
    if not x_forwarded_proto:
        return

    # Proxy headers present - check if Uvicorn trusted them by verifying
    # that request.url.scheme was updated to match X-Forwarded-Proto.
    # If Uvicorn didn't trust the source IP, it would ignore the header
    # and request.url.scheme would still be "http" (the actual protocol).
    if request.url.scheme != x_forwarded_proto.lower():
        # Headers were sent but not trusted - fail closed
        client_ip = request.client.host if request.client else "unknown"
        forwarded_allow_ips = os.getenv("FORWARDED_ALLOW_IPS", "0.0.0.0/0")
        error_id = str(uuid.uuid4())

        # Log basic rejection at INFO level (always visible, helps spot misconfiguration)
        logger.info(
            "Request rejected: untrusted proxy headers",
            error_id=error_id,
            client_ip=client_ip,
            x_forwarded_proto=x_forwarded_proto,
        )

        # Log detailed debugging info at DEBUG level (for deeper troubleshooting)
        logger.debug(
            "Proxy header validation failed - debug details",
            error_id=error_id,
            client_ip=client_ip,
            x_forwarded_proto=x_forwarded_proto,
            request_scheme=request.url.scheme,
            forwarded_allow_ips=forwarded_allow_ips,
            fix_option_1=f"Set FORWARDED_ALLOW_IPS={client_ip}",
            fix_option_2="Set FORWARDED_ALLOW_IPS=0.0.0.0/0 to trust all",
        )

        # Return generic error with error ID so user can share with admin
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied. Please contact your administrator. (Error ID: {error_id})",
        )


@router.get("/login")
async def login(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    redirect_uri: str = "/",
    backup: bool = False,
):
    # ===== SECURITY: Validate Proxy Headers =====
    _validate_proxy_headers(request)
    # ===== END SECURITY VALIDATION =====

    # ===== DEBUG: Request Connection & Headers =====
    logger.debug(
        "LOGIN ENDPOINT DEBUG",
        # Connection info
        client_ip=request.client.host if request.client else "unknown",
        client_port=request.client.port if request.client else "unknown",
        # Request URL components
        request_url_full=str(request.url),
        request_scheme=request.url.scheme,
        request_host=request.url.netloc,
        request_path=request.url.path,
        request_query=request.url.query,
        # Query parameters passed in
        redirect_uri_param=redirect_uri,
        backup_param=backup,
        # All proxy headers
        x_forwarded_proto=request.headers.get("X-Forwarded-Proto"),
        x_forwarded_host=request.headers.get("X-Forwarded-Host"),
        x_forwarded_for=request.headers.get("X-Forwarded-For"),
        x_forwarded_port=request.headers.get("X-Forwarded-Port"),
        # Request headers
        host_header=request.headers.get("Host"),
        user_agent=request.headers.get("User-Agent"),
        # Scope details (raw ASGI scope)
        asgi_scheme=request.scope.get("scheme"),
        asgi_server_host=request.scope.get("server", ["?", "?"])[0],
        asgi_server_port=request.scope.get("server", ["?", "?"])[1],
    )
    # ===== END DEBUG =====

    # ===== SECURITY WARNING: Proxy Headers with Permissive Config =====
    # Warn if proxy headers are detected but FORWARDED_ALLOW_IPS allows all IPs
    if request.headers.get("X-Forwarded-Proto"):
        forwarded_allow_ips = os.getenv("FORWARDED_ALLOW_IPS", "0.0.0.0/0")
        if forwarded_allow_ips in ("0.0.0.0/0", "*"):
            logger.warning(
                "SECURITY WARNING: Proxy headers detected (X-Forwarded-Proto) but "
                "FORWARDED_ALLOW_IPS is set to allow all IPs (0.0.0.0/0). "
                "For production use, set FORWARDED_ALLOW_IPS to your reverse proxy IP(s) only. "
                "This prevents header spoofing attacks. "
                "See documentation: https://github.com/markbeep/AudioBookRequest/docs/oidc"
            )
    # ===== END SECURITY WARNING =====

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

    # DEBUG: Show what we're building the redirect URI from
    logger.debug(
        "OIDC_CONFIG_DEBUG",
        oidc_authorize_endpoint=authorize_endpoint,
        oidc_client_id=client_id,
        oidc_scope=scope,
    )

    auth_redirect_uri = urljoin(str(request.url), "/auth/oidc")

    # DEBUG: Show the built redirect URI
    logger.debug(
        "REDIRECT_URI_BUILD_DEBUG",
        request_url_before_join=str(request.url),
        path_being_joined="/auth/oidc",
        final_auth_redirect_uri=auth_redirect_uri,
        scheme_of_redirect_uri=auth_redirect_uri.split("://")[0] if "://" in auth_redirect_uri else "UNKNOWN",
    )

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


@router.post("/logout")
async def logout(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    _: Annotated[DetailedUser, Security(ABRAuth())],
):
    request.session["sub"] = ""

    login_type = auth_config.get_login_type(session)
    if login_type == LoginTypeEnum.oidc:
        logout_url = oidc_config.get(session, "oidc_logout_url")
        if logout_url:
            return Response(
                status_code=status.HTTP_204_NO_CONTENT,
                headers={"HX-Redirect": logout_url},
            )
    return Response(
        status_code=status.HTTP_204_NO_CONTENT, headers={"HX-Redirect": "/login"}
    )


@router.post("/token")
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
    return Response(
        status_code=status.HTTP_200_OK, headers={"HX-Redirect": redirect_uri}
    )


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
    # ===== SECURITY: Validate Proxy Headers =====
    _validate_proxy_headers(request)
    # ===== END SECURITY VALIDATION =====

    # ===== DEBUG: OIDC Callback Request =====
    logger.debug(
        "OIDC_CALLBACK_DEBUG",
        # Connection info
        client_ip=request.client.host if request.client else "unknown",
        # Request URL components
        request_url_full=str(request.url),
        request_scheme=request.url.scheme,
        request_host=request.url.netloc,
        request_path=request.url.path,
        # Query parameters
        code_param=code[:20] + "..." if len(code) > 20 else code,
        state_param=state[:20] + "..." if state and len(state) > 20 else state,
        # Proxy headers
        x_forwarded_proto=request.headers.get("X-Forwarded-Proto"),
        x_forwarded_host=request.headers.get("X-Forwarded-Host"),
        x_forwarded_for=request.headers.get("X-Forwarded-For"),
        asgi_scheme=request.scope.get("scheme"),
    )
    # ===== END DEBUG =====

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

    # DEBUG: Show the redirect URI being sent to token endpoint
    logger.debug(
        "OIDC_CALLBACK_REDIRECT_URI_DEBUG",
        request_url_for_join=str(request.url),
        final_auth_redirect_uri=auth_redirect_uri,
        scheme=auth_redirect_uri.split("://")[0] if "://" in auth_redirect_uri else "UNKNOWN",
    )

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
