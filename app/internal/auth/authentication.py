import secrets
import time
from datetime import datetime
from math import inf
from typing import Annotated, final

import pydantic
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, Request, status
from fastapi.openapi.models import SecurityBase as SecurityBaseModel
from fastapi.openapi.models import SecuritySchemeType
from fastapi.security import (
    HTTPBasic,
    HTTPBearer,
    OpenIdConnect,
)
from fastapi.security.base import SecurityBase
from sqlmodel import Session, select

from app.internal.auth.config import auth_config
from app.internal.auth.login_types import LoginTypeEnum
from app.internal.models import APIKey, GroupEnum, User
from app.util.censor import censor
from app.util.db import get_session
from app.util.log import logger

ph = PasswordHasher()


class DetailedUser(User):
    login_type: LoginTypeEnum

    def can_logout(self):
        return self.login_type in [LoginTypeEnum.forms, LoginTypeEnum.oidc]


def raise_for_invalid_password(
    session: Session,
    password: str,
    confirm_password: str | None = None,
    ignore_confirm: bool = False,
):
    if not ignore_confirm and password != confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passwords must be equal",
        )

    min_password_length = auth_config.get_min_password_length(session)
    if not len(password) >= min_password_length:
        logger.warning(
            "Password does not meet minimum length requirement",
            min_length=min_password_length,
            actual_length=len(password),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Password must be at least {min_password_length} characters long",
        )


def is_correct_password(user: User, password: str) -> bool:
    try:
        return ph.verify(user.password, password)
    except VerifyMismatchError:
        return False


def authenticate_user(session: Session, username: str, password: str) -> User | None:
    user = session.get(User, username)
    if not user:
        return None

    try:
        ph.verify(user.password, password)
    except VerifyMismatchError:
        return None

    if ph.check_needs_rehash(user.password):
        user.password = ph.hash(password)
        session.add(user)
        session.commit()

    return user


def create_user(
    username: str,
    password: str,
    group: GroupEnum = GroupEnum.untrusted,
    root: bool = False,
    extra_data: str | None = None,
) -> User:
    password_hash = ph.hash(password)
    return User(
        username=username,
        password=password_hash,
        group=group,
        root=root,
        extra_data=extra_data,
    )


def generate_api_key() -> str:
    return secrets.token_urlsafe(32)


def create_api_key(
    user: User,
    name: str,
) -> tuple[APIKey, str]:
    private_key = generate_api_key()
    key_hash = ph.hash(private_key)
    api_key = APIKey(
        user_username=user.username,
        name=name,
        key_hash=key_hash,
    )
    return api_key, private_key


@final
class APIKeyAuth(SecurityBase):
    def __init__(
        self,
        lowest_allowed_group: GroupEnum = GroupEnum.untrusted,
        auto_error: bool = True,
    ):
        self.auto_error = auto_error
        self.api_key_header = HTTPBearer(auto_error=auto_error)
        self.model = self.api_key_header.model
        self.scheme_name = lowest_allowed_group.capitalize() + " API Key"
        self.lowest_allowed_group = lowest_allowed_group

    async def __call__(
        self,
        request: Request,
        session: Annotated[Session, Depends(get_session)],
    ) -> DetailedUser | None:
        api_key = await self.api_key_header(request)
        if api_key is None:
            if self.auto_error:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing API key"
                )
            return None
        user = self._authenticate_api_key(session, api_key.credentials)
        if user is None:
            if self.auto_error:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key"
                )
            return None
        if not user.is_above(self.lowest_allowed_group):
            if self.auto_error:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden"
                )
            return None
        user = DetailedUser.model_validate(
            user, update={"login_type": LoginTypeEnum.api_key}
        )
        return user

    def _authenticate_api_key(self, session: Session, key: str) -> User | None:
        api_keys = session.exec(select(APIKey)).all()

        for api_key in api_keys:
            try:
                ph.verify(api_key.key_hash, key)
            except VerifyMismatchError:
                continue

            user = session.get(User, api_key.user_username)
            if not user:
                logger.error(
                    f"API key {api_key.id} references non-existent user {api_key.user_username}"
                )
                continue

            api_key.last_used = datetime.now()
            session.add(api_key)
            session.commit()

            return user

        return None


class RequiresLoginException(Exception):
    def __init__(self, detail: str | None = None, **kwargs: object):
        super().__init__(**kwargs)
        self.detail: str | None = detail


@final
class ABRAuth(SecurityBase):
    def __init__(self, lowest_allowed_group: GroupEnum = GroupEnum.untrusted):
        self.lowest_allowed_group = lowest_allowed_group
        self.oidc_scheme: OpenIdConnect | None = None
        self.none_user: User | None = None
        self.security = HTTPBasic()
        self.model = SecurityBaseModel(
            type=SecuritySchemeType.openIdConnect, description="ABR Authentication"
        )
        self.scheme_name = lowest_allowed_group.capitalize() + " ABR Authentication"

    async def __call__(
        self,
        request: Request,
        session: Annotated[Session, Depends(get_session)],
    ) -> DetailedUser:
        login_type = auth_config.get_login_type(session)

        logger.debug(
            "Checking user authentication",
            url=request.url,
            login_type=login_type,
            lowest_allowed_group=self.lowest_allowed_group,
        )
        if login_type == LoginTypeEnum.forms:
            standard_user = await self._get_session_auth(request, session)
        elif login_type == LoginTypeEnum.none:
            standard_user = await self._get_none_auth(session)
        elif login_type == LoginTypeEnum.oidc:
            standard_user = await self._get_oidc_auth(request, session)
        else:
            standard_user = await self._get_basic_auth(request, session)

        if not standard_user.is_above(self.lowest_allowed_group):
            logger.warning(
                "User does not have sufficient permissions",
                username=censor(standard_user.username),
                group=standard_user.group,
                lowest_allowed_group=self.lowest_allowed_group,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden"
            )

        try:
            user = DetailedUser.model_validate(
                standard_user, update={"login_type": login_type}
            )
        except pydantic.ValidationError as e:
            logger.error(
                "Failed to validate user model",
                exc_info=e,
                user=standard_user.model_dump(),
            )
            raise RequiresLoginException(
                "Failed to validate user model. Please log in again."
            )

        logger.debug(
            "User authenticated successfully",
            username=censor(user.username),
            group=user.group,
            login_type=login_type,
        )
        return user

    async def _get_basic_auth(
        self,
        request: Request,
        session: Session,
    ) -> User:
        logger.debug("Getting user from basic auth", url=request.url)

        invalid_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )

        credentials = await self.security(request)
        if not credentials:
            logger.debug("No credentials provided")
            raise invalid_exception

        user = authenticate_user(session, credentials.username, credentials.password)
        if not user:
            logger.debug(
                "Invalid username or password", username=censor(credentials.username)
            )
            raise invalid_exception

        logger.debug("Logged in with basic auth", username=censor(user.username))
        return user

    async def _get_session_auth(
        self,
        request: Request,
        session: Session,
    ) -> User:
        logger.debug("Getting user from session", url=request.url)
        # It's enough to get the username from the signed session cookie
        username = request.session.get("sub")
        if not username or not isinstance(username, str):
            logger.debug("No username found in session sub")
            raise RequiresLoginException()

        user = session.get(User, username)
        if not user:
            logger.debug("User does not exist", username=censor(username))
            raise RequiresLoginException("User does not exist")

        logger.debug("Logged in with session", username=censor(user.username))
        return user

    async def _get_oidc_auth(
        self,
        request: Request,
        session: Session,
    ) -> User:
        logger.debug("Getting user from OIDC session", url=request.url)
        if request.session.get("exp", inf) < time.time():
            logger.debug("OIDC session expired", exp=request.session.get("exp"))
            raise RequiresLoginException()
        return await self._get_session_auth(request, session)

    async def _get_none_auth(self, session: Session) -> User:
        """Treats every request as being root by returning the first admin user"""
        if self.none_user:
            logger.debug(
                "Using none auth, returning cached admin user",
                username=censor(self.none_user.username),
                group=self.none_user.group,
            )
            return self.none_user

        user = session.exec(
            select(User).where(User.group == GroupEnum.admin).limit(1)
        ).one()
        self.none_user = User.model_validate(user)

        logger.debug(
            "Using none auth, returning newly fetched admin user",
            username=censor(self.none_user.username),
            group=self.none_user.group,
        )
        return user


@final
class AnyAuth(SecurityBase):
    """
    Allows authentication using either a bearer-token or by
    sending along a valid session-token in the cookies
    """

    def __init__(
        self,
        lowest_allowed_group: GroupEnum = GroupEnum.untrusted,
        auto_error: bool = True,
    ):
        self.lowest_allowed_group = lowest_allowed_group
        self.auto_error = auto_error
        self.api_key_auth = APIKeyAuth(lowest_allowed_group, auto_error)
        self.abr_auth = ABRAuth(lowest_allowed_group)
        self.scheme_name = lowest_allowed_group.capitalize() + " Auth"
        self.model = HTTPBearer(description="API Key or Session cookies").model

    async def __call__(
        self,
        request: Request,
        session: Annotated[Session, Depends(get_session)],
    ) -> DetailedUser | None:
        try:
            user = await self.api_key_auth(request, session)
            if user:
                return user
        except HTTPException:
            pass

        try:
            user = await self.abr_auth(request, session)
            if user:
                return user
        except RequiresLoginException:
            pass

        if self.auto_error:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )
        return None
