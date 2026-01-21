import hashlib
from os import PathLike
from pathlib import Path
from typing import Annotated, Callable
from urllib.parse import urlencode

import aiohttp
from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, Security
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from app.internal.auth.authentication import (
    ABRAuth,
    DetailedUser,
    create_user,
    raise_for_invalid_password,
)
from app.internal.auth.config import auth_config
from app.internal.auth.login_types import LoginTypeEnum
from app.internal.env_settings import Settings
from app.internal.indexers.mam import fetch_mam_book_details, MamIndexer, ValuedMamConfigurations, SessionContainer
from app.internal.indexers.configuration import create_valued_configuration
from app.internal.models import GroupEnum, Audiobook, AudiobookRequest, Config
from app.util.connection import get_connection
from app.util.db import get_session
from app.util.log import logger
from app.util.redirect import BaseUrlRedirectResponse
from app.util.templates import templates, template_response

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


@router.get("/book/{asin}")
async def get_book_details_page(
    request: Request,
    asin: str,
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[aiohttp.ClientSession, Depends(get_connection)],
    user: Annotated[DetailedUser, Security(ABRAuth())],
):
    book = session.exec(select(Audiobook).where(Audiobook.asin == asin)).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    mam_meta_config = session.exec(select(Config).where(Config.key == "mam_metadata_enabled")).first()
    mam_enabled = mam_meta_config.value == "True" if mam_meta_config else False

    mam_data = None
    if mam_enabled:
        logger.debug("MAM integration is active, checking metadata", book=book.title)
        config_obj = await MamIndexer.get_configurations(
            SessionContainer(session=session, client_session=client_session)
        )
        valued = create_valued_configuration(config_obj, session)
        mam_config = ValuedMamConfigurations(
            mam_session_id=str(getattr(valued, "mam_session_id") or "")
        )
        
        if not mam_config.mam_session_id:
            logger.warning("MAM metadata is enabled but no session ID is set")
        else:
            req = session.exec(select(AudiobookRequest).where(AudiobookRequest.asin == asin)).first()

            if req and req.mam_id:
                mam_data = await fetch_mam_book_details(
                    container=SessionContainer(session=session, client_session=client_session),
                    configurations=mam_config,
                    mam_id=req.mam_id,
                )
            else:
                # Try a lookup by title since we don't have an ID link yet
                from urllib.parse import urlencode, urljoin
                from app.internal.indexers.mam import MAM_HEADERS
                from app.internal.indexers.mam_models import _MamResponse

                search_url = urljoin(
                    "https://www.myanonamouse.net",
                    f"/tor/js/loadSearchJSONbasic.php?{urlencode({
                        'tor[text]': book.title,
                        'tor[main_cat]': '13',
                        'tor[searchIn]': 'torrents',
                        'tor[searchType]': 'active',
                        'startNumber': 0,
                        'perpage': 5,
                    }, doseq=True)}",
                )
                
                try:
                    async with client_session.get(search_url, cookies={"mam_id": mam_config.mam_session_id}, headers=MAM_HEADERS) as resp:
                        if resp.ok:
                            json_data = await resp.json()
                            if "data" in json_data:
                                results = _MamResponse.model_validate(json_data)
                                if results.data:
                                    mam_data = results.data[0]
                except Exception as e:
                    logger.error("Failed to lookup book on MAM", error=str(e))

    return template_response(
        "book_details.html",
        request,
        user,
        {"book": book, "mam_data": mam_data},
    )

@router.get("/book-details-modal/{asin}")
async def get_book_details_modal(
    request: Request,
    asin: str,
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[aiohttp.ClientSession, Depends(get_connection)],
    user: Annotated[DetailedUser, Security(ABRAuth())],
):
    book = session.exec(select(Audiobook).where(Audiobook.asin == asin)).first()

    mam_data = None
    if book and Settings().app.mam_metadata_enabled:
        config_obj = await MamIndexer.get_configurations(
            SessionContainer(session=session, client_session=client_session)
        )
        valued = create_valued_configuration(config_obj, session)
        mam_config = ValuedMamConfigurations(
            mam_session_id=str(getattr(valued, "mam_session_id") or "")
        )
        req = session.exec(select(AudiobookRequest).where(AudiobookRequest.asin == asin)).first()

        if req and req.mam_id:
            mam_data = await fetch_mam_book_details(
                container=SessionContainer(session=session, client_session=client_session),
                configurations=mam_config,
                mam_id=req.mam_id,
            )

    return template_response(
        "components/book_details_modal.html",
        request,
        user,
        {"book": book, "mam_data": mam_data},
    )

@router.get("/book/{asin}/download-opf")
async def download_opf_file(
    asin: str,
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[aiohttp.ClientSession, Depends(get_connection)],
    user: Annotated[DetailedUser, Security(ABRAuth())],
):
    book = session.exec(select(Audiobook).where(Audiobook.asin == asin)).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    mam_meta_config = session.exec(select(Config).where(Config.key == "mam_metadata_enabled")).first()
    mam_enabled = mam_meta_config.value == "True" if mam_meta_config else False

    if not mam_enabled:
        raise HTTPException(status_code=400, detail="MAM Metadata is disabled")

    config_obj = await MamIndexer.get_configurations(
        SessionContainer(session=session, client_session=client_session)
    )
    valued = create_valued_configuration(config_obj, session)
    mam_config = ValuedMamConfigurations(
        mam_session_id=str(getattr(valued, "mam_session_id") or "")
    )

    if not mam_config.mam_session_id:
        raise HTTPException(status_code=400, detail="MAM is not configured")

    mam_data = None
    req = session.exec(select(AudiobookRequest).where(AudiobookRequest.asin == asin)).first()

    if req and req.mam_id:
        mam_data = await fetch_mam_book_details(
            container=SessionContainer(session=session, client_session=client_session),
            configurations=mam_config,
            mam_id=req.mam_id,
        )
    else:
        from urllib.parse import urlencode, urljoin
        from app.internal.indexers.mam import MAM_HEADERS
        from app.internal.indexers.mam_models import _MamResponse

        search_url = urljoin(
            "https://www.myanonamouse.net",
            f"/tor/js/loadSearchJSONbasic.php?{urlencode({
                'tor[text]': book.title,
                'tor[main_cat]': '13',
                'tor[searchIn]': 'torrents',
                'tor[searchType]': 'active',
                'startNumber': 0,
                'perpage': 5,
            }, doseq=True)}",
        )
        try:
            async with client_session.get(search_url, cookies={"mam_id": mam_config.mam_session_id}, headers=MAM_HEADERS) as resp:
                if resp.ok:
                    json_data = await resp.json()
                    if "data" in json_data:
                        results = _MamResponse.model_validate(json_data)
                        if results.data:
                            mam_data = results.data[0]
        except Exception:
            pass

    if not mam_data:
        raise HTTPException(status_code=404, detail="Could not find metadata for this book")

    from app.internal.metadata import generate_opf_for_mam
    content = generate_opf_for_mam(mam_data)
    
    # Store temporary file
    temp = Path("/tmp/audiobook_metadata")
    temp.mkdir(parents=True, exist_ok=True)
    
    clean_name = "".join([c for c in book.title if c.isalnum() or c in (' ', '.', '_')]).rstrip()
    fname = f"{clean_name}.opf"
    fpath = temp / f"{asin}.opf"

    with open(fpath, "w", encoding="utf-8") as f:
        f.write(content)

    return FileResponse(
        path=fpath,
        filename=fname,
        media_type="application/xml",
    )

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


@router.get("/init")
def read_init(request: Request, session: Annotated[Session, Depends(get_session)]):
    init_username = Settings().app.init_root_username.strip()
    init_password = Settings().app.init_root_password.strip()

    try:
        login_type = Settings().app.get_force_login_type()
        if login_type == LoginTypeEnum.oidc and (
            not init_username.strip() or not init_password.strip()
        ):
            raise ValueError(
                "OIDC login type is not supported for initial setup without an initial username/password."
            )
    except ValueError as e:
        logger.error(f"Invalid force login type: {e}")
        login_type = None

    if init_username and init_password:
        logger.info(
            "Initial root credentials provided. Skipping init page.",
            username=init_username,
            login_type=login_type,
        )
        if not login_type:
            logger.warning(
                "No login type set. Defaulting to 'forms'.", username=init_username
            )
            login_type = LoginTypeEnum.forms

        user = create_user(init_username, init_password, GroupEnum.admin, root=True)
        session.add(user)
        auth_config.set_login_type(session, login_type)
        session.commit()
        return BaseUrlRedirectResponse("/")

    elif init_username or init_password:
        logger.warning(
            "Initial root credentials provided but missing either username or password. Skipping initialization through environment variables.",
            set_username=bool(init_username),
            set_password=bool(init_password),
        )

    return templates.TemplateResponse(
        "init.html",
        {
            "request": request,
            "hide_navbar": True,
            "force_login_type": login_type,
        },
    )


@router.post("/init")
def create_init(
    request: Request,
    login_type: Annotated[LoginTypeEnum, Form()],
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    confirm_password: Annotated[str, Form()],
    session: Annotated[Session, Depends(get_session)],
):
    if username.strip() == "":
        return templates.TemplateResponse(
            "init.html",
            {"request": request, "error": "Invalid username"},
            block_name="init_messages",
        )

    try:
        raise_for_invalid_password(session, password, confirm_password)
    except HTTPException as e:
        return templates.TemplateResponse(
            "init.html",
            {"request": request, "error": e.detail},
            block_name="init_messages",
        )

    user = create_user(username, password, GroupEnum.admin, root=True)
    session.add(user)
    auth_config.set_login_type(session, login_type)
    session.commit()

    return Response(status_code=201, headers={"HX-Redirect": "/"})


@router.get("/login")
def redirect_login(request: Request):
    return BaseUrlRedirectResponse("/auth/login?" + urlencode(request.query_params))