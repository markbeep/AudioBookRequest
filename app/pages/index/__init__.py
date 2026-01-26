from typing import Annotated
from urllib.parse import urlencode

from aiohttp import ClientSession
from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    Security,
)
from htpy import a, div, h1, p, span
from htpy.starlette import HtpyResponse
from sqlmodel import Session

from app.components.base_layout import base_layout
from app.components.icons.search import search_icon
from app.internal.auth.authentication import (
    ABRAuth,
    DetailedUser,
    create_user,
    raise_for_invalid_password,
)
from app.internal.auth.config import auth_config
from app.internal.auth.login_types import LoginTypeEnum
from app.internal.book_search import audible_region_type
from app.internal.env_settings import Settings
from app.internal.models import GroupEnum
from app.pages.index.categories import categories, categories_hx
from app.pages.index.for_you import for_you, for_you_hx, popular_hx
from app.routers.api.recommendations import (
    get_user_recommendations as api_get_user_recommendations,
    get_popular_recommendations as api_get_popular_recommendations,
    get_category_recommendations as api_get_category_recommendations,
)
from app.util.connection import get_connection
from app.util.db import get_session
from app.util.log import logger
from app.util.redirect import BaseUrlRedirectResponse
from app.util.templates import templates

router = APIRouter()


@router.get("/")
def read_root(user: Annotated[DetailedUser, Security(ABRAuth())]):
    base_url = Settings().app.base_url

    return HtpyResponse(
        base_layout(user_can_logout=user.can_logout())[
            div(
                ".w-screen.flex.flex-col.items-center.justify-center.p-6.sm:p-8.overflow-x-hidden.gap-6"
            )[
                div(".w-full.max-w-7xl")[
                    div(".flex.justify-between.items-center.mb-4")[
                        div[
                            h1(".text-4xl.font-bold.text-left")[
                                f"Welcome, {user.username}!"
                            ],
                            p(".text-lg.opacity-70.mt-1")[
                                "Discover your next great audiobook"
                            ],
                        ],
                        a(
                            ".btn.btn-primary.flex.items-center.gap-2",
                            href=f"{base_url}/search",
                            title="Search for books",
                        )[span["Search Books"], search_icon()],
                    ]
                ],
                for_you(
                    title="For You",
                    description="Personalized recommendations based on your requests",
                    link=f"{base_url}/recommendations/for-you",
                    hx_get=f"{base_url}/hx/for-you",
                ),
                for_you(
                    title="Popular",
                    description="The most popular books on the instance",
                    link=f"{base_url}/recommendations/popular",
                    hx_get=f"{base_url}/hx/popular",
                ),
                categories(),
            ]
        ]
    )


@router.get("/hx/for-you")
async def get_user_recommendations(
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    user: Annotated[DetailedUser, Security(ABRAuth())],
    seed_asins: Annotated[list[str] | None, Query(alias="seed_asins")] = None,
    limit: int = 20,
):
    result = await api_get_user_recommendations(
        session=session,
        client_session=client_session,
        user=user,
        seed_asins=seed_asins,
        limit=limit,
    )
    return HtpyResponse(for_you_hx(recommendations=result))


@router.get("/hx/popular")
async def get_popular_recommendations(
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(ABRAuth())],
    min_requests: int = 1,
    limit: int = 10,
    exclude_downloaded: bool = True,
):
    result = await api_get_popular_recommendations(
        session=session,
        user=user,
        min_requests=min_requests,
        limit=limit,
        exclude_downloaded=exclude_downloaded,
    )
    return HtpyResponse(popular_hx(popular=result))


@router.get("/hx/categories")
async def get_category_recommendations(
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    user: Annotated[DetailedUser, Security(ABRAuth())],
    audible_region: audible_region_type | None = None,
):
    result = await api_get_category_recommendations(
        session=session,
        client_session=client_session,
        user=user,
        audible_region=audible_region,
    )
    return HtpyResponse(categories_hx(recommendations=result))


"""


Backwards compatibility for login
TODO: remove and separate into internal logic and minimal init/login pages 


"""


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
