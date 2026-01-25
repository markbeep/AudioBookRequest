from typing import Annotated

from aiohttp import ClientSession
from fastapi import APIRouter, Depends, Query, Security
from htpy import a, div, h1, p, span
from htpy.starlette import HtpyResponse
from sqlmodel import Session

from app.components.base_layout import base_layout
from app.components.icons.search import search_icon
from app.internal.auth.authentication import ABRAuth, DetailedUser
from app.internal.book_search import audible_region_type
from app.internal.env_settings import Settings
from app.pages.index.categories import categories, categories_hx
from app.pages.index.for_you import for_you, for_you_hx, popular_hx
from app.routers.api.recommendations import (
    get_user_recommendations as api_get_user_recommendations,
    get_popular_recommendations as api_get_popular_recommendations,
    get_category_recommendations as api_get_category_recommendations,
)
from app.util.connection import get_connection
from app.util.db import get_session

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
