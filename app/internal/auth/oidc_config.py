from typing import Literal

from aiohttp import ClientSession
from pydantic import BaseModel
from sqlmodel import Session

from app.util.cache import StringConfigCache
from app.util.log import logger


oidcConfigKey = Literal[
    "oidc_client_id",
    "oidc_client_secret",
    "oidc_scope",
    "oidc_username_claim",
    "oidc_group_claim",
    "oidc_endpoint",
    "oidc_token_endpoint",
    "oidc_userinfo_endpoint",
    "oidc_authorize_endpoint",
    "oidc_redirect_scheme",
    "oidc_logout_url",
]


class InvalidOIDCConfiguration(Exception):
    def __init__(self, detail: str | None = None, **kwargs: object):
        super().__init__(**kwargs)
        self.detail: str | None = detail


class _OidcResponse(BaseModel):
    authorization_endpoint: str
    token_endpoint: str
    userinfo_endpoint: str
    end_session_endpoint: str | None = None


class _OidcScopeResponse(BaseModel):
    scopes_supported: list[str] = []
    claims_supported: list[str] = []


class oidcConfig(StringConfigCache[oidcConfigKey]):
    async def set_endpoint(
        self,
        session: Session,
        client_session: ClientSession,
        endpoint: str,
    ):
        self.set(session, "oidc_endpoint", endpoint)
        try:
            async with client_session.get(endpoint) as response:
                if response.status == 200:
                    data = _OidcResponse.model_validate(await response.json())
                    self.set(
                        session,
                        "oidc_authorize_endpoint",
                        data.authorization_endpoint,
                    )
                    self.set(session, "oidc_token_endpoint", data.token_endpoint)
                    self.set(session, "oidc_userinfo_endpoint", data.userinfo_endpoint)
                    if data.end_session_endpoint and not self.get(
                        session, "oidc_logout_url"
                    ):
                        self.set(session, "oidc_logout_url", data.end_session_endpoint)
        except Exception as e:
            logger.error(f"Failed to set OIDC endpoint: {endpoint}. Error: {str(e)}")
            raise InvalidOIDCConfiguration(
                f"Failed to set OIDC endpoint: {endpoint}. Error: {str(e)}"
            ) from None

    def get_redirect_scheme(self, session: Session) -> str:
        """Returns 'auto', 'http', or 'https'. Defaults to 'auto'."""
        value = self.get(session, "oidc_redirect_scheme", "auto")
        if value in ("http", "https"):
            return value
        return "auto"

    async def validate(
        self, session: Session, client_session: ClientSession
    ) -> str | None:
        """
        Returns None if valid, the error message otherwise
        """
        endpoint = self.get(session, "oidc_endpoint")
        if not endpoint:
            return "Missing OIDC endpoint"
        async with client_session.get(endpoint) as response:
            if not response.ok:
                return "Failed to fetch OIDC configuration"
            data = _OidcScopeResponse.model_validate(await response.json())

        config_scope = self.get(session, "oidc_scope", "").split(" ")
        provider_scope = data.scopes_supported
        if not provider_scope or not all(
            scope in provider_scope for scope in config_scope
        ):
            not_supported = set(config_scope) - set(provider_scope)
            return f"Scopes are not all supported by the provider: [{', '.join(not_supported)}]"

        provider_claims = data.claims_supported
        if not provider_claims:
            return "Provider does not support or list claims"

        username_claim = self.get(session, "oidc_username_claim")
        if not username_claim or username_claim not in provider_claims:
            return "Username claim is not supported by the provider"

        group_claim = self.get(session, "oidc_group_claim")
        if group_claim and group_claim not in provider_claims:
            return "Group claim is not supported by the provider"


oidc_config = oidcConfig()
