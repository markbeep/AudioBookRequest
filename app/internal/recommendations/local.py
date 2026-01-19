from datetime import datetime, timedelta
from typing import Counter, Sequence
from pydantic import BaseModel
from sqlalchemy.sql.functions import count
from sqlmodel import Session, col, select

from app.internal.models import Audiobook, AudiobookRequest
from app.util.log import logger


class AudiobookPopularity(BaseModel):
    book: Audiobook
    request_count: int

    def requested_amount(self) -> str:
        return f"{self.request_count} request{'s' if self.request_count != 1 else ''}"


def get_popular_books(
    session: Session,
    limit: int = 10,
    min_requests: int = 1,  # Lower default minimum
    exclude_downloaded: bool = True,
    exclude_requested_username: str | None = None,
) -> list[AudiobookPopularity]:
    """Get the most popular books based on how many users have requested them."""

    query = (
        select(
            Audiobook,
            request_count := count(col(AudiobookRequest.user_username)),
        )
        .join(AudiobookRequest)
        .group_by(AudiobookRequest.asin)
        .having(request_count >= min_requests)
        .order_by(request_count.desc(), col(AudiobookRequest.updated_at).desc())
        .limit(limit)
    )

    if exclude_downloaded:
        query = query.where(~col(Audiobook.downloaded))
    if exclude_requested_username:
        query = query.having(
            col(Audiobook.asin).not_in(
                select(AudiobookRequest.asin).where(
                    AudiobookRequest.user_username == exclude_requested_username
                )
            )
        )

    results = session.exec(query).all()
    logger.debug(f"Popular books query returned {len(results)} results")

    popular: list[AudiobookPopularity] = []
    for book, request_count in results:
        popular.append(
            AudiobookPopularity(
                book=book,
                request_count=request_count,
            )
        )
        logger.debug(f"Popular book: {book.asin} (requests: {request_count})")

    return popular


def get_recently_requested_books(
    session: Session,
    limit: int = 10,
    days_back: int = 30,
    exclude_downloaded: bool = True,
    exclude_requested_username: str | None = None,
) -> Sequence[Audiobook]:
    """Get recently requested books within the specified time frame."""
    cutoff_date = datetime.now() - timedelta(days=days_back)

    query = (
        select(Audiobook)
        .join(AudiobookRequest)
        .where(
            AudiobookRequest.updated_at >= cutoff_date,
            AudiobookRequest.user_username != exclude_requested_username,
        )
        .order_by(col(AudiobookRequest.updated_at).desc())
        .limit(limit)
        .distinct()
    )

    if exclude_downloaded:
        query = query.where(~col(Audiobook.downloaded))

    results = session.exec(query).all()
    logger.debug(f"Recently requested books query returned {len(results)} results")

    return results


class AuthorNarrators(BaseModel):
    authors: list[str]
    narrators: list[str]


def get_most_popular_authors(
    session: Session,
    limit: int = 10,
    exclude_downloaded: bool = True,
    username: str | None = None,
) -> AuthorNarrators:
    """Get the most popular authors based on how many users have requested their books."""

    query = select(Audiobook).join(AudiobookRequest).distinct()
    if exclude_downloaded:
        query = query.where(~col(Audiobook.downloaded))
    if username:
        query = query.where(AudiobookRequest.user_username == username)
    audiobooks = session.exec(query).all()
    author_counter = Counter[str]()
    narrator_counter = Counter[str]()
    for book in audiobooks:
        author_counter.update(book.authors)
        narrator_counter.update(book.narrators)

    popular_authors = author_counter.most_common(limit)
    popular_narrators = narrator_counter.most_common(limit)
    return AuthorNarrators(
        authors=[author for author, _ in popular_authors],
        narrators=[narrator for narrator, _ in popular_narrators],
    )
