import os
import re
from pathlib import Path
from typing import Awaitable, Callable
from urllib.parse import quote_plus, urlencode

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware import Middleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlmodel import select

from app.internal.auth.authentication import RequiresLoginException
from app.internal.auth.config import auth_config, initialize_force_login_type
from app.internal.auth.oidc_config import InvalidOIDCConfiguration
from app.internal.auth.session_middleware import (
    DynamicSessionMiddleware,
    middleware_linker,
)
from app.internal.book_search import clear_old_book_caches
from app.internal.env_settings import Settings
from app.internal.models import User
from app.routers import api
from app.util.db import get_session
from app.util.log import logger
from app.util.redirect import BaseUrlRedirectResponse

with next(get_session()) as session:
    auth_secret = auth_config.get_auth_secret(session)
    initialize_force_login_type(session)
    clear_old_book_caches(session)


app = FastAPI(
    title="AudioBookRequest",
    debug=Settings().app.debug,
    openapi_url="/openapi.json" if Settings().app.openapi_enabled else None,
    description="API for AudiobookRequest",
    middleware=[
        Middleware(DynamicSessionMiddleware, auth_secret, middleware_linker),
        Middleware(GZipMiddleware),
    ],
    root_path=Settings().app.base_url.rstrip("/"),
    redirect_slashes=False,
)

app.include_router(api.router)

user_exists = False


@app.exception_handler(RequiresLoginException)
async def redirect_to_login(request: Request, exc: RequiresLoginException):
    if request.method == "GET":
        params: dict[str, str] = {}
        if exc.detail:
            params["error"] = exc.detail
        path = request.url.path
        if path != "/" and not path.startswith("/login"):
            params["redirect_uri"] = path
        return BaseUrlRedirectResponse("/login?" + urlencode(params))
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


@app.exception_handler(InvalidOIDCConfiguration)
async def redirect_to_invalid_oidc(request: Request, exc: InvalidOIDCConfiguration):
    _ = request
    path = "/api/auth/invalid-oidc"
    if exc.detail:
        path += f"?error={quote_plus(exc.detail)}"
    return BaseUrlRedirectResponse(path)


@app.middleware("http")
async def redirect_to_init(
    request: Request,
    call_next: Callable[[Request], Awaitable[StreamingResponse]],
):
    """
    Initial redirect if no user exists. We force the user to create a new login
    """
    global user_exists
    if (
        not user_exists
        and not request.url.path.startswith("/auth")
        and not request.url.path.startswith("/astro")
        and not request.url.path.startswith("/api")
        and not request.url.path.startswith("/openapi.json")
        and not request.url.path.startswith("/docs")
        and request.method == "GET"
    ):
        with next(get_session()) as session:
            user_count = session.exec(select(func.count()).select_from(User)).one()
            if user_count == 0:
                return BaseUrlRedirectResponse("/auth/init")
            else:
                user_exists = True
    elif user_exists and request.url.path.startswith("/auth/init"):
        return BaseUrlRedirectResponse("/")
    response = await call_next(request)
    return response


@app.get("{file_path:path}", include_in_schema=False)
async def astro_files(request: Request, file_path: str):
    # -----------------------------------------
    # | Prevent directory traversal.          |
    # | Frontend directory HAS to be          |
    # | made absolute before comparing.       |
    # -----------------------------------------
    frontend_path = Path(Settings().internal.frontend_dir).absolute()
    requested_path = frontend_path / file_path.removeprefix("/astro").lstrip("/")
    shared_path = os.path.commonprefix(
        [frontend_path, os.path.realpath(requested_path)]
    )
    if shared_path != str(frontend_path):
        logger.warning(
            "Directory traversal attempt detected", requested_path=requested_path
        )
        raise HTTPException(status_code=404, detail="Not found")
    # -----------------------------------------

    requested_file = frontend_path / requested_path
    if not requested_file.exists() or not requested_file.is_file():
        requested_file /= "index.html"
        if not requested_file.exists() or not requested_file.is_file():
            raise HTTPException(status_code=404, detail="Not Found")

    # Determine media type based on file extension
    extension = requested_file.suffix.lower()
    media_types = {
        ".html": "text/html",
        ".css": "text/css",
        ".js": "application/javascript",
        ".json": "application/json",
        ".xml": "application/xml",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".svg": "image/svg+xml",
        ".ico": "image/x-icon",
        ".woff": "font/woff",
        ".woff2": "font/woff2",
        ".ttf": "font/ttf",
        ".eot": "application/vnd.ms-fontobject",
        ".otf": "font/otf",
    }
    media_type = media_types.get(extension, "application/octet-stream")

    # if a theme is given in the cookies, we adjust the html file to use that theme
    # to prevent any flickering on the client-side
    if requested_file.suffix == ".html" and (theme := request.cookies.get("theme")):
        with requested_file.open("r") as f:
            file_content = f.read()
            file_content = re.sub(
                r'data-theme="\w+"', f'data-theme="{theme}"', file_content, count=1
            )
            return StreamingResponse(
                iter([file_content.encode("utf-8")]), media_type=media_type
            )

    else:
        return StreamingResponse(requested_file.open("rb"), media_type=media_type)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=Settings().internal.api_port,
    )
