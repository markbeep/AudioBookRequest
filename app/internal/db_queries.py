from typing import Literal, Sequence, cast

from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import InstrumentedAttribute, selectinload
from sqlmodel import Session, asc, col, not_, select

from app.internal.models import (
    Audiobook,
    AudiobookRequest,
    AudiobookWishlistResult,
    ManualBookRequest,
    User,
)


class WishlistCounts(BaseModel):
    requests: int
    downloaded: int
    manual: int


def get_wishlist_counts(session: Session, user: User | None = None) -> WishlistCounts:
    """
    If a non-admin user is given, only count requests for that user.
    Admins can see and get counts for all requests.
    """
    username = None if user is None or user.is_admin() else user.username

    rows = session.exec(
        select(Audiobook.downloaded, func.count("*"))
        .where(not username or AudiobookRequest.user_username == username)
        .select_from(Audiobook)
        .join(AudiobookRequest)
        .group_by(col(Audiobook.downloaded))
    ).all()
    requests = 0
    downloaded = 0
    for downloaded_status, count in rows:
        if downloaded_status:
            downloaded = count
        else:
            requests = count

    manual = session.exec(
        select(func.count())
        .select_from(ManualBookRequest)
        .where(
            not username or ManualBookRequest.user_username == username,
            col(ManualBookRequest.user_username).is_not(None),
        )
    ).one()

    return WishlistCounts(
        requests=requests,
        downloaded=downloaded,
        manual=manual,
    )


def get_wishlist_results(
    session: Session,
    username: str | None = None,
    response_type: Literal["all", "downloaded", "not_downloaded"] = "all",
) -> list[AudiobookWishlistResult]:
    """
    Gets the books that have been requested. If a username is given only the books requested by that
    user are returned. If no username is given, all book requests are returned.
    """
    match response_type:
        case "downloaded":
            clause = Audiobook.downloaded
        case "not_downloaded":
            clause = not_(Audiobook.downloaded)
        case _:
            clause = True

    results = session.exec(
        select(Audiobook)
        .where(
            clause,
            col(Audiobook.asin).in_(
                select(AudiobookRequest.asin).where(
                    not username or AudiobookRequest.user_username == username
                )
            ),
        )
        .options(
            selectinload(
                cast(
                    InstrumentedAttribute[list[AudiobookRequest]],
                    cast(object, Audiobook.requests),
                )
            )
        )
    ).all()

    return [
        AudiobookWishlistResult(
            book=book,
            requests=book.requests,
        )
        for book in results
    ]


def get_all_manual_requests(
    session: Session, user: User
) -> Sequence[ManualBookRequest]:
    return session.exec(
        select(ManualBookRequest)
        .where(
            user.is_admin() or ManualBookRequest.user_username == user.username,
            col(ManualBookRequest.user_username).is_not(None),
        )
        .order_by(asc(ManualBookRequest.downloaded))
    ).all()
