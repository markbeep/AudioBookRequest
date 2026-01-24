from typing import Literal, Sequence, cast

from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import InstrumentedAttribute, selectinload
from sqlmodel import Session, asc, col, not_, select, or_

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
    downloading: int


def get_wishlist_counts(session: Session, user: User | None = None) -> WishlistCounts:
    """
    If a non-admin user is given, only count requests for that user.
    Admins can see and get counts for all requests.
    """
    username = None if user is None or user.is_admin() else user.username

    # 1. Count strictly "Requested" (Not downloaded, not downloading)
    requests_query = select(func.count(Audiobook.asin.distinct())).join(AudiobookRequest).where(
        Audiobook.downloaded == False,
        AudiobookRequest.torrent_hash == None,
        AudiobookRequest.processing_status == "pending"
    )
    if username:
        requests_query = requests_query.where(AudiobookRequest.user_username == username)
    requests = session.exec(requests_query).one()

    # 2. Count "Downloading" (Actively in qB or being processed)
    # Using processing_status is faster than hitting qB every time
    downloading_query = select(func.count(AudiobookRequest.asin.distinct())).join(Audiobook).where(
        Audiobook.downloaded == False,
        col(AudiobookRequest.processing_status).in_(["download_initiated", "generating_metadata", "organizing", "importing"])
    )
    if username:
        downloading_query = downloading_query.where(AudiobookRequest.user_username == username)
    downloading_count = session.exec(downloading_query).one()

    # 3. Count "Downloaded" (Is downloaded and has a request)
    downloaded_query = select(func.count(Audiobook.asin.distinct())).join(AudiobookRequest).where(
        Audiobook.downloaded == True
    )
    if username:
        downloaded_query = downloaded_query.where(AudiobookRequest.user_username == username)
    downloaded = session.exec(downloaded_query).one()

    # 4. Count "Manual"
    manual_query = select(func.count()).select_from(ManualBookRequest).where(
        col(ManualBookRequest.user_username).is_not(None)
    )
    if username:
        manual_query = manual_query.where(ManualBookRequest.user_username == username)
    manual = session.exec(manual_query).one()

    return WishlistCounts(
        requests=requests,
        downloaded=downloaded,
        manual=manual,
        downloading=downloading_count,
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
    statement = select(Audiobook).distinct()

    if response_type == "not_downloaded":
        # Join to filter by request status
        statement = statement.join(AudiobookRequest)
        statement = statement.where(
            not_(Audiobook.downloaded),
            AudiobookRequest.torrent_hash == None,
            AudiobookRequest.processing_status == "pending"
        )
        if username:
            statement = statement.where(AudiobookRequest.user_username == username)
    else:
        if response_type == "downloaded":
            statement = statement.where(Audiobook.downloaded == True)
        
        # Filter for books that have a request (by this user if specified)
        subquery = select(AudiobookRequest.asin)
        if username:
            subquery = subquery.where(AudiobookRequest.user_username == username)
        
        statement = statement.where(col(Audiobook.asin).in_(subquery))

    results = session.exec(
        statement
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
