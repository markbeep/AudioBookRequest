import json

from aiohttp import ClientSession, InvalidUrlClientError
from sqlmodel import Session, select

from app.internal.models import (
    Audiobook,
    EventEnum,
    ManualBookRequest,
    Notification,
    NotificationBodyTypeEnum,
    User,
)
from app.util import json_type
from app.util.db import get_session
from app.util.log import logger

PLACEHOLDER_COVER_URL = "https://picsum.photos/id/24/500/500"


def _replace_variables(
    template: str,
    /,
    users: list[User] | None = None,
    book_title: str | None = None,
    book_authors: str | None = None,
    book_narrators: str | None = None,
    book_cover: str | None = None,
    event_type: str | None = None,
    other_replacements: dict[str, str] | None = None,
):
    if other_replacements is None:
        other_replacements = {}
    if users:
        user = users[0]
        template = template.replace("{eventUser}", user.username)
        if user.extra_data:
            template = template.replace("{eventUserExtraData}", user.extra_data)
        joined = ", ".join([u.username for u in users])
        template = template.replace("{joinedUsers}", joined)
        joined_extra = ", ".join([u.extra_data for u in users if u.extra_data])
        if joined_extra:
            template = template.replace("{joinedUsersExtraData}", joined_extra)

    if book_title:
        template = template.replace("{bookTitle}", book_title)
    if book_authors:
        template = template.replace("{bookAuthors}", book_authors)
    if book_narrators:
        template = template.replace("{bookNarrators}", book_narrators)
    if book_cover:
        template = template.replace("{bookCover}", book_cover)
    else:
        template = template.replace("{bookCover}", PLACEHOLDER_COVER_URL)
    if event_type:
        template = template.replace("{eventType}", event_type)

    for key, value in other_replacements.items():
        template = template.replace(f"{{{key}}}", value)

    return template


async def _send(
    body: str | dict[str, json_type.JSON],
    notification: Notification,
    client_session: ClientSession,
):
    try:
        if notification.body_type == NotificationBodyTypeEnum.json:
            async with client_session.post(
                notification.url,
                json=body,
                headers=notification.headers,
            ) as response:
                response.raise_for_status()
                return await response.text()
        elif notification.body_type == NotificationBodyTypeEnum.text:
            async with client_session.post(
                notification.url,
                data=body,
                headers=notification.headers,
            ) as response:
                response.raise_for_status()
                return await response.text()
    except InvalidUrlClientError:
        logger.error("Failed to send notification. Invalid URL", url=notification.url)
        raise ValueError(f"Invalid URL: url={notification.url}") from None


async def send_notification(
    session: Session,
    notification: Notification,
    book_asin: str | None = None,
    other_replacements: dict[str, str] | None = None,
) -> str | None:
    if other_replacements is None:
        other_replacements = {}
    book_title = None
    book_authors = None
    book_narrators = None
    book_cover = None
    requesters: list[User] | None = None
    if book_asin:
        book = session.exec(
            select(Audiobook).where(Audiobook.asin == book_asin)
        ).first()
        if book:
            book_title = book.title
            book_authors = ",".join(book.authors)
            book_narrators = ",".join(book.narrators)
            book_cover = book.cover_image
            requesters = [req.user for req in book.requests]

        if "bookASIN" not in other_replacements:
            other_replacements["bookASIN"] = book_asin

    body = _replace_variables(
        notification.body,
        users=requesters,
        book_title=book_title,
        book_authors=book_authors,
        book_narrators=book_narrators,
        book_cover=book_cover,
        event_type=notification.event.value,
        other_replacements=other_replacements,
    )

    if notification.body_type == NotificationBodyTypeEnum.json:
        body = json.loads(body, strict=False)  # pyright: ignore[reportAny]

    logger.info(
        "Sending notification",
        url=notification.url,
        body=body,
        event_type=notification.event.value,
        body_type=notification.body_type.value,
        headers=notification.headers,
    )

    try:
        async with ClientSession() as client_session:
            resp = await _send(body, notification, client_session)
        logger.info(
            "Individual notification sent successfully",
            url=notification.url,
            response=resp,
        )
        return resp
    except Exception as e:
        logger.error(
            "Failed to send individual notification",
            url=notification.url,
            body=body,
            error=str(e),
        )
        raise


async def send_all_notifications(
    event_type: EventEnum,
    book_asin: str | None = None,
    other_replacements: dict[str, str] | None = None,
):
    if other_replacements is None:
        other_replacements = {}
    with next(get_session()) as session:
        notifications = session.exec(
            select(Notification).where(
                Notification.event == event_type, Notification.enabled
            )
        ).all()
        for notification in notifications:
            await send_notification(
                session=session,
                notification=notification,
                book_asin=book_asin,
                other_replacements=other_replacements,
            )


async def send_manual_notification(
    notification: Notification,
    book: ManualBookRequest,
    requester: User | None = None,
    other_replacements: dict[str, str] | None = None,
):
    """Send a notification for manual book requests"""
    if other_replacements is None:
        other_replacements = {}
    try:
        book_authors = ",".join(book.authors)
        book_narrators = ",".join(book.narrators)

        body = _replace_variables(
            notification.body,
            users=[requester] if requester else None,
            book_title=book.title,
            book_authors=book_authors,
            book_narrators=book_narrators,
            event_type=notification.event.value,
            other_replacements=other_replacements,
        )

        if notification.body_type == NotificationBodyTypeEnum.json:
            body = json.loads(body)  # pyright: ignore[reportAny]

        logger.info(
            "Sending manual notification",
            url=notification.url,
            body=body,
            event_type=notification.event.value,
            body_type=notification.body_type.value,
            headers=notification.headers,
        )

        async with ClientSession() as client_session:
            return await _send(body, notification, client_session)

    except Exception as e:
        logger.error("Failed to send manual notification", error=str(e))
        return None


async def send_all_manual_notifications(
    event_type: EventEnum,
    book_request: ManualBookRequest,
    other_replacements: dict[str, str] | None = None,
):
    if other_replacements is None:
        other_replacements = {}
    with next(get_session()) as session:
        user = session.exec(
            select(User).where(User.username == book_request.user_username)
        ).first()
        notifications = session.exec(
            select(Notification).where(
                Notification.event == event_type, Notification.enabled
            )
        ).all()
        for notif in notifications:
            await send_manual_notification(
                notification=notif,
                book=book_request,
                requester=user,
                other_replacements=other_replacements,
            )
