import base64
import secrets
from typing import Literal

from sqlmodel import Session

from app.internal.auth.login_types import LoginTypeEnum
from app.internal.auth.session_middleware import middleware_linker
from app.internal.env_settings import Settings
from app.util.cache import StringConfigCache
from app.util.log import logger
from app.util.time import Minute, Second

AuthConfigKey = Literal[
    "login_type",
    "access_token_expiry_minutes",
    "auth_secret",
    "min_password_length",
]


class AuthConfig(StringConfigCache[AuthConfigKey]):
    def get_login_type(self, session: Session) -> LoginTypeEnum:
        login_type = self.get(session, "login_type")
        if login_type:
            return LoginTypeEnum(login_type)
        return LoginTypeEnum.not_set

    def set_login_type(self, session: Session, login_Type: LoginTypeEnum):
        self.set(session, "login_type", login_Type.value)

    def reset_auth_secret(self, session: Session):
        auth_secret = base64.encodebytes(secrets.token_bytes(64)).decode("utf-8")
        middleware_linker.update_secret(auth_secret)
        self.set(session, "auth_secret", auth_secret)

    def get_auth_secret(self, session: Session) -> str:
        auth_secret = self.get(session, "auth_secret")
        if auth_secret:
            return auth_secret
        auth_secret = base64.encodebytes(secrets.token_bytes(64)).decode("utf-8")
        self.set(session, "auth_secret", auth_secret)
        return auth_secret

    def get_access_token_expiry_minutes(self, session: Session) -> Minute:
        return Minute(self.get_int(session, "access_token_expiry_minutes", 60 * 24 * 7))

    def set_access_token_expiry_minutes(self, session: Session, expiry: Minute):
        middleware_linker.update_max_age(Second(expiry * 60))
        self.set_int(session, "access_token_expiry_minutes", expiry)

    def get_min_password_length(self, session: Session) -> int:
        return self.get_int(session, "min_password_length", 1)

    def set_min_password_length(self, session: Session, min_password_length: int):
        self.set_int(session, "min_password_length", min_password_length)


auth_config = AuthConfig()


# force login type if enabled
def initialize_force_login_type(session: Session):
    login_type = auth_config.get(session, "login_type")
    try:
        force_login_type = Settings().app.get_force_login_type()
    except Exception as e:
        logger.error(f"Failed to get force login type: {e}")
        force_login_type = None
    if not login_type:
        if force_login_type:
            logger.debug(
                "Application has not been initialized yet, ignoring force login type."
            )
        return
    if force_login_type and force_login_type != LoginTypeEnum(login_type):
        logger.info(
            f"Force login type is set to {force_login_type}, overriding current login type: {login_type}"
        )
        auth_config.set_login_type(session, force_login_type)
