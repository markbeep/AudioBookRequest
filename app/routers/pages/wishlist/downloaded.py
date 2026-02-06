from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Security
from sqlmodel import Session

from app.internal.audiobookshelf.client import background_abs_trigger_scan
from app.internal.audiobookshelf.config import abs_config
from app.internal.auth.authentication import ABRAuth, DetailedUser
from app.internal.db_queries import get_wishlist_counts, get_wishlist_results
from app.internal.models import GroupEnum
from app.routers.api.requests import mark_downloaded as api_mark_downloaded
from app.util.db import get_session
from app.util.templates import catalog_response

router = APIRouter(prefix="/downloaded")


@router.get("")
async def downloaded(
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(ABRAuth())],
):
    username = None if user.is_admin() else user.username
    results = get_wishlist_results(session, username, "downloaded")
    counts = get_wishlist_counts(session, user)
    return catalog_response(
        "Wishlist.Downloaded",
        user=user,
        results=results,
        counts=counts,
    )


@router.patch("/hx-add/{asin}")
async def update_downloaded(
    asin: str,
    session: Annotated[Session, Depends(get_session)],
    background_task: BackgroundTasks,
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    await api_mark_downloaded(asin, session, background_task, admin_user)

    username = None if admin_user.is_admin() else admin_user.username
    results = get_wishlist_results(session, username, "not_downloaded")
    counts = get_wishlist_counts(session, admin_user)

    if abs_config.is_valid(session):
        background_task.add_task(background_abs_trigger_scan)

    return catalog_response(
        "Wishlist.Wishlist",
        user=admin_user,
        results=results,
        page="wishlist",
        counts=counts,
        update_tablist=True,
    )
