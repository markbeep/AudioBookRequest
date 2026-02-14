import base64
import secrets
import time
from typing import Annotated, cast

import jwt
from aiohttp import ClientSession
from fastapi import (
    APIRouter,
    Depends,
    Request,
    Response,
    status,
)
from pydantic import BaseModel
from sqlmodel import Session, select

from app.internal.auth.authentication import (
    create_user,
)
from app.internal.auth.config import auth_config
from app.internal.auth.login_types import LoginTypeEnum
from app.internal.auth.oidc_config import InvalidOIDCConfiguration, oidc_config
from app.internal.models import GroupEnum, User
from app.util.censor import censor
from app.util.connection import USER_AGENT, get_connection
from app.util.db import get_session
from app.util.log import logger
from app.util.templates import catalog_response

router = APIRouter(prefix="/oidc")


class _AccessTokenBody(BaseModel):
    access_token: str | None = None
    expires_in: int | None = None


@router.get("")
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

    auth_redirect_uri = str(request.url_for("login_oidc"))
    scheme = oidc_config.get_redirect_scheme(session)
    if scheme == "http":
        auth_redirect_uri = auth_redirect_uri.replace("https:", "http:")
    elif scheme == "https":
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
                username=censor(username),
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

    # NOTE: We can't redirect server side, because that results in an infinite loop.
    # The session token is never correctly set causing any other endpoint to
    # redirect to the login page which in turn starts the OIDC flow again.
    # The redirect page allows for the cookie to properly be set on the browser
    # and then redirects client-side.
    return catalog_response("Redirect", redirect_uri=redirect_uri)


@router.get("/invalid")
def invalid_oidc(
    session: Annotated[Session, Depends(get_session)],
    error: str | None = None,
):
    if auth_config.get_login_type(session) != LoginTypeEnum.oidc:
        return Response(status_code=status.HTTP_404_NOT_FOUND)
    return catalog_response("Auth.OIDC.Invalid", error=error)
