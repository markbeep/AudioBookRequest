from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from starlette.datastructures import URL

from app.internal.env_settings import Settings


class BaseUrlRedirectResponse(RedirectResponse):
    """
    Redirects while preserving the base URL
    """

    def __init__(self, url: str | URL, status_code: int = 302) -> None:
        if (
            isinstance(url, str)
            and url.startswith("/")
            or isinstance(url, URL)
            and url.path.startswith("/")
        ):
            url = f"{Settings().app.base_url.rstrip('/')}{url}"
        super().__init__(
            url=url,
            status_code=status_code,
        )


class ClientRedirectResponse(BaseModel):
    redirect: str | None
