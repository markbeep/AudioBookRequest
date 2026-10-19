from typing import Annotated

from fastapi import APIRouter, Depends, Security
from sqlmodel import Session, col, select

from app.internal.auth.authentication import ABRAuth, DetailedUser
from app.internal.models import FavoriteAuthor
from app.util.db import get_session
from app.util.templates import catalog_response

router = APIRouter()


@router.get("/favorite-authors")
async def favorite_authors(
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(ABRAuth())],
):
    authors = session.exec(
        select(FavoriteAuthor.author)
        .where(col(FavoriteAuthor.user_username) == user.username)
        .order_by(col(FavoriteAuthor.author))
    ).all()
    return catalog_response("FavoriteAuthors.Index", user=user, authors=authors)
