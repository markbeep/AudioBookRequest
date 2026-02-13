# pyright: reportUnknownMemberType=false

import html
import json
from typing import Any, Literal, Mapping

import markdown
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader
from jinja2_fragments.fastapi import Jinja2Blocks
from jinja2_htmlmin import minify_loader
from jinjax import Catalog
from jinjax.jinjax import JinjaX
from starlette.background import BackgroundTask

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


def _to_js_string(val: str | int | float) -> str:
    return html.escape(f"'{str(val).replace("'", "\\'").replace('\n', '\\n')}'")


# filters
templates.env.filters["toJSstring"] = _to_js_string
# globals
templates.env.globals["getattr"] = getattr
templates.env.globals["version"] = Settings().app.version
templates.env.globals["json_regexp"] = (
    r'^\{\s*(?:"[^"\\]*(?:\\.[^"\\]*)*"\s*:\s*"[^"\\]*(?:\\.[^"\\]*)*"\s*(?:,\s*"[^"\\]*(?:\\.[^"\\]*)*"\s*:\s*"[^"\\]*(?:\\.[^"\\]*)*"\s*)*)?\}$'
)
templates.env.globals["base_url"] = Settings().app.base_url.rstrip("/")

with open("CHANGELOG.md", "r") as file:
    changelog_content = file.read()
templates.env.globals["changelog"] = markdown.markdown(changelog_content)


templates.env.add_extension(JinjaX)
catalog = Catalog(jinja_env=templates.env)  # pyright: ignore[reportUnknownArgumentType]
catalog.add_folder("templates/components")
catalog.add_folder("templates/pages")
catalog.add_folder("templates/layouts")


def catalog_response(
    name: str,
    status_code: int = 200,
    headers: Mapping[str, str] | None = None,
    media_type: str | None = None,
    background: BackgroundTask | None = None,
    **kwargs: Any,  # pyright: ignore[reportExplicitAny, reportAny]
):
    return HTMLResponse(
        catalog.render(name, **kwargs),  # pyright: ignore[reportAny]
        status_code=status_code,
        headers=headers,
        media_type=media_type,
        background=background,
    )


def catalog_response_toast(
    name: str,
    message: str,
    toast_type: Literal["error", "success", "info"],
    status_code: int = 200,
    headers: dict[str, str] | None = None,
    media_type: str | None = None,
    background: BackgroundTask | None = None,
    **kwargs: Any,  # pyright: ignore[reportExplicitAny, reportAny]
):
    if headers is None:
        headers = {}
    headers["HX-Trigger"] = json.dumps(
        {"toast": {"type": toast_type, "message": message}}
    )

    return catalog_response(
        name,
        status_code=status_code,
        headers=headers,
        media_type=media_type,
        background=background,
        **kwargs,
    )
