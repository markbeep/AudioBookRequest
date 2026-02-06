from typing import Annotated

from aiohttp import ClientSession
from fastapi import APIRouter, Depends, Security
from sqlmodel import Session

from app.internal.auth.authentication import ABRAuth, DetailedUser
from app.internal.db_queries import get_wishlist_counts, get_wishlist_results
from app.internal.models import GroupEnum
from app.routers.api.requests import delete_request as api_delete_request
from app.routers.api.requests import start_auto_download_endpoint
from app.util.connection import get_connection
from app.util.db import get_session
from app.util.templates import catalog_response

from . import downloaded, manual, sources

router = APIRouter(prefix="/wishlist")

router.include_router(downloaded.router)
router.include_router(manual.router)
router.include_router(sources.router)


@router.get("")
async def wishlist(
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(ABRAuth())],
):
    username = None if user.is_admin() else user.username
    results = get_wishlist_results(session, username, "not_downloaded")
    counts = get_wishlist_counts(session, user)
    return catalog_response(
        "Wishlist.Index",
        user=user,
        results=results,
        counts=counts,
    )


@router.post("/hx-auto-download/{asin}")
async def start_auto_download(
    asin: str,
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.trusted))],
):
    await start_auto_download_endpoint(asin, session, client_session, user)
    username = None if user.is_admin() else user.username
    results = get_wishlist_results(session, username, "not_downloaded")
    counts = get_wishlist_counts(session, user)

    return catalog_response(
        "Wishlist.Wishlist",
        user=user,
        results=results,
        page="wishlist",
        counts=counts,
        update_tablist=True,
    )


@router.delete("/hx-delete/{asin}")
async def delete_request(
    asin: str,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(ABRAuth())],
    downloaded: bool | None = None,
):
    await api_delete_request(asin, session, user)

    counts = get_wishlist_counts(session, user)

    if downloaded:  # download page
        results = get_wishlist_results(
            session,
            None if user.is_admin() else user.username,
            "downloaded",
        )
        return catalog_response(
            "Wishlist.Wishlist",
            user=user,
            results=results,
            page="downloaded",
            counts=counts,
            update_tablist=True,
        )
    else:
        results = get_wishlist_results(
            session,
            None if user.is_admin() else user.username,
            "not_downloaded",
        )
        return catalog_response(
            "Wishlist.Wishlist",
            user=user,
            results=results,
            page="wishlist",
            counts=counts,
            update_tablist=True,
        )
