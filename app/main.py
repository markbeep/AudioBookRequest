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
from app.routers import api, auth, root, search, settings, wishlist
from app.util.db import get_session
from app.util.fetch_js import fetch_scripts
from app.util.redirect import BaseUrlRedirectResponse
from app.util.templates import templates
from app.util.toast import ToastException

# intialize js dependencies or throw an error if not in debug mode
fetch_scripts(Settings().app.debug)

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

app.include_router(auth.router, include_in_schema=False)
app.include_router(root.router, include_in_schema=False)
app.include_router(search.router, include_in_schema=False)
app.include_router(settings.router, include_in_schema=False)
app.include_router(wishlist.router, include_in_schema=False)
# api router under /api
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
    path = "/auth/invalid-oidc"
    if exc.detail:
        path += f"?error={quote_plus(exc.detail)}"
    return BaseUrlRedirectResponse(path)


@app.exception_handler(ToastException)
async def raise_toast(request: Request, exc: ToastException):
    context: dict[str, Request | str] = {"request": request}
    if exc.type == "error":
        context["toast_error"] = exc.message
    elif exc.type == "success":
        context["toast_success"] = exc.message
    elif exc.type == "info":
        context["toast_info"] = exc.message

    return templates.TemplateResponse(
        "base.html",
        context,
        block_name="toast_block",
        headers={"HX-Retarget": "#toast-block"}
        | ({"HX-Refresh": "true"} if exc.force_refresh else {}),
    )


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
        and request.url.path != "/init"
        and not request.url.path.startswith("/static")
        and request.method == "GET"
    ):
        with next(get_session()) as session:
            user_count = session.exec(select(func.count()).select_from(User)).one()
            if user_count == 0:
                return BaseUrlRedirectResponse("/init")
            else:
                user_exists = True
    elif user_exists and request.url.path.startswith("/init"):
        return BaseUrlRedirectResponse("/")
    response = await call_next(request)
    return response
