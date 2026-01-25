# pyright: reportUnknownMemberType=false

import html
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


def _zfill(val: str | int | float, num: int) -> str:
    return str(val).zfill(num)


def _to_js_string(val: str | int | float) -> str:
    return html.escape(f"'{str(val).replace("'", "\\'").replace('\n', '\\n')}'")


def _basename(path: str) -> str:
    import os

    if "|" in path:
        parts = path.split("|")
        base = os.path.basename(parts[0])
        if len(parts) > 1:
            return f"{base} (+{len(parts) - 1} others)"
        return base
    return os.path.basename(path)


def _asin_to_cover(asin: str) -> str:
    from app.util.db import get_session
    from app.internal.models import Audiobook

    with next(get_session()) as session:
        book = session.get(Audiobook, asin)
        return book.cover_image if book else ""


def _asin_to_title(asin: str) -> str:
    from app.util.db import get_session
    from app.internal.models import Audiobook

    with next(get_session()) as session:
        book = session.get(Audiobook, asin)
        return book.title if book else "Unknown"


def _asin_to_author(asin: str) -> str:
    from app.util.db import get_session
    from app.internal.models import Audiobook

    with next(get_session()) as session:
        book = session.get(Audiobook, asin)
        return ", ".join(book.authors) if book and book.authors else "Unknown"


templates.env.filters["zfill"] = _zfill
templates.env.filters["toJSstring"] = _to_js_string
templates.env.filters["basename"] = _basename
templates.env.filters["asin_to_cover"] = _asin_to_cover
templates.env.filters["asin_to_title"] = _asin_to_title
templates.env.filters["asin_to_author"] = _asin_to_author
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
    context: dict[str, Any],  # pyright: ignore[reportExplicitAny]
    status_code: int = 200,
    headers: Mapping[str, str] | None = None,
    media_type: str | None = None,
    background: BackgroundTask | None = None,
    *,
    block_names: list[str] = ...,
) -> Response: ...


@overload
def template_response(
    name: str,
    request: Request,
    user: DetailedUser,
    context: dict[str, Any],  # pyright: ignore[reportExplicitAny]
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
    context: dict[str, Any],  # pyright: ignore[reportExplicitAny]
    status_code: int = 200,
    headers: Mapping[str, str] | None = None,
    media_type: str | None = None,
    background: BackgroundTask | None = None,
    **kwargs: Any,  # pyright: ignore[reportAny, reportExplicitAny]
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
        **kwargs,  # pyright: ignore[reportAny]
    )
