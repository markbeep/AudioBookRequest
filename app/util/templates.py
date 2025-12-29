from jinja2_htmlmin import minify_loader
from jinja2 import Environment, FileSystemLoader
from typing import Any, Mapping, overload

import markdown
from fastapi import Request, Response
from jinja2_fragments.fastapi import Jinja2Blocks
from starlette.background import BackgroundTask

from app.internal.auth.authentication import DetailedUser
from app.internal.env_settings import Settings

templates = Jinja2Blocks(
    env=Environment(
        loader=minify_loader(
            FileSystemLoader("templates"),
            remove_comments=True,  # pyrefly: ignore[bad-argument-type]
            remove_empty_space=True,  # pyrefly: ignore[bad-argument-type]
            remove_all_empty_space=True,  # pyrefly: ignore[bad-argument-type]
            reduce_boolean_attributes=True,  # pyrefly: ignore[bad-argument-type]
        )
    )
)

templates.env.filters["zfill"] = lambda val, num: str(val).zfill(num)
templates.env.filters["toJSstring"] = (
    lambda val: f"'{str(val).replace("'", "\\'").replace('\n', '\\n')}'"
)
templates.env.globals["vars"] = vars
templates.env.globals["getattr"] = getattr
templates.env.globals["version"] = Settings().app.version
templates.env.globals["json_regexp"] = (
    r'^\{\s*(?:"[^"\\]*(?:\\.[^"\\]*)*"\s*:\s*"[^"\\]*(?:\\.[^"\\]*)*"\s*(?:,\s*"[^"\\]*(?:\\.[^"\\]*)*"\s*:\s*"[^"\\]*(?:\\.[^"\\]*)*"\s*)*)?\}$'
)
templates.env.globals["base_url"] = Settings().app.base_url.rstrip("/")

with open("CHANGELOG.md", "r") as file:
    changelog_content = file.read()
templates.env.globals["changelog"] = markdown.markdown(changelog_content)


@overload
def template_response(
    name: str,
    request: Request,
    user: DetailedUser,
    context: dict[str, Any],
    status_code: int = 200,
    headers: Mapping[str, str] | None = None,
    media_type: str | None = None,
    background: BackgroundTask | None = None,
    *,
    block_names: list[str] = [],
) -> Response: ...


@overload
def template_response(
    name: str,
    request: Request,
    user: DetailedUser,
    context: dict[str, Any],
    status_code: int = 200,
    headers: Mapping[str, str] | None = None,
    media_type: str | None = None,
    background: BackgroundTask | None = None,
    *,
    block_name: str | None = None,
) -> Response: ...


def template_response(
    name: str,
    request: Request,
    user: DetailedUser,
    context: dict[str, Any],
    status_code: int = 200,
    headers: Mapping[str, str] | None = None,
    media_type: str | None = None,
    background: BackgroundTask | None = None,
    **kwargs: Any,
) -> Response:
    """Template response wrapper to make sure required arguments are passed everywhere"""
    copy = context.copy()
    copy.update({"request": request, "user": user})

    return templates.TemplateResponse(
        name=name,
        context=copy,
        status_code=status_code,
        headers=headers,
        media_type=media_type,
        background=background,
        **kwargs,
    )
