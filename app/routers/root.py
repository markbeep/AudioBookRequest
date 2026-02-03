import hashlib
from os import PathLike
from pathlib import Path
from typing import Annotated, Callable
from urllib.parse import urlencode

from fastapi import APIRouter, Request, Security
from fastapi.responses import FileResponse

from app.internal.auth.authentication import ABRAuth, DetailedUser
from app.internal.env_settings import Settings
from app.util.redirect import BaseUrlRedirectResponse
from app.util.templates import templates

router = APIRouter()


root = Path("static")

etag_cache: dict[PathLike[str] | str, str] = {}


def add_cache_headers(func: Callable[..., FileResponse]):
    def wrapper(v: object):
        _ = v
        file = func()
        etag = etag_cache.get(file.path)
        if not etag or Settings().app.debug:
            with open(file.path, "rb") as f:
                etag = hashlib.sha1(f.read(), usedforsecurity=False).hexdigest()
            etag_cache[file.path] = etag

        file.headers.append("Etag", etag)
        # cache for a year. All static files should do cache busting with `?v=<version>`
        file.headers.append("Cache-Control", f"public, max-age={60 * 60 * 24 * 365}")
        return file

    return wrapper


@router.get("/static/globals.css")
@add_cache_headers
def read_globals_css():
    return FileResponse(root / "globals.css", media_type="text/css")


@router.get("/static/nouislider.css")
@add_cache_headers
def read_nouislider_css():
    return FileResponse(root / "nouislider.min.css", media_type="text/css")


@router.get("/static/nouislider.js")
@add_cache_headers
def read_nouislider_js():
    return FileResponse(root / "nouislider.min.js", media_type="text/javascript")


@router.get("/static/apple-touch-icon.png")
@add_cache_headers
def read_apple_touch_icon():
    return FileResponse(root / "apple-touch-icon.png", media_type="image/png")


@router.get("/static/favicon-32x32.png")
@add_cache_headers
def read_favicon_32():
    return FileResponse(root / "favicon-32x32.png", media_type="image/png")


@router.get("/static/favicon-16x16.png")
@add_cache_headers
def read_favicon_16():
    return FileResponse(root / "favicon-16x16.png", media_type="image/png")


@router.get("/static/site.webmanifest")
@add_cache_headers
def read_site_webmanifest():
    return FileResponse(
        root / "site.webmanifest", media_type="application/manifest+json"
    )


@router.get("/static/htmx.js")
@add_cache_headers
def read_htmx():
    return FileResponse(root / "htmx.js", media_type="text/javascript")


@router.get("/static/htmx-preload.js")
@add_cache_headers
def read_htmx_preload():
    return FileResponse(root / "htmx-preload.js", media_type="text/javascript")


@router.get("/static/alpine.js")
@add_cache_headers
def read_alpinejs():
    return FileResponse(root / "alpine.js", media_type="text/javascript")


@router.get("/static/toastify.js")
@add_cache_headers
def read_toastifyjs():
    return FileResponse(root / "toastify.js", media_type="text/javascript")


@router.get("/static/toastify.css")
@add_cache_headers
def read_toastifycss():
    return FileResponse(root / "toastify.css", media_type="text/css")


@router.get("/static/favicon.svg")
@add_cache_headers
def read_favicon_svg():
    return FileResponse(root / "favicon.svg", media_type="image/svg+xml")


@router.get("/")
def read_root(request: Request, user: Annotated[DetailedUser, Security(ABRAuth())]):
    return templates.TemplateResponse(
        "root.html",
        {
            "request": request,
            "user": user,
            "initial_page": True,
        },
    )


@router.get("/login")
def redirect_login(request: Request):
    return BaseUrlRedirectResponse("/auth/login?" + urlencode(request.query_params))
