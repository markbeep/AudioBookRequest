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


def _replace_variables(
    template: str,
    user: User | None = None,
    book_title: str | None = None,
    book_authors: str | None = None,
    book_narrators: str | None = None,
    event_type: str | None = None,
    other_replacements: dict[str, str] | None = None,
):
    if other_replacements is None:
        other_replacements = {}
    if user:
        template = template.replace("{eventUser}", user.username)
        if user.extra_data:
            template = template.replace("{eventUserExtraData}", user.extra_data)
    if book_title:
        template = template.replace("{bookTitle}", book_title)
    if book_authors:
        template = template.replace("{bookAuthors}", book_authors)
    if book_narrators:
        template = template.replace("{bookNarrators}", book_narrators)
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
    requester: User | None = None,
    book_asin: str | None = None,
    other_replacements: dict[str, str] | None = None,
):
    if other_replacements is None:
        other_replacements = {}
    book_title = None
    book_authors = None
    book_narrators = None
    if book_asin:
        book = session.exec(
            select(Audiobook).where(Audiobook.asin == book_asin)
        ).first()
        if book:
            book_title = book.title
            book_authors = ",".join(book.authors)
            book_narrators = ",".join(book.narrators)

    body = _replace_variables(
        notification.body,
        requester,
        book_title,
        book_authors,
        book_narrators,
        notification.event.value,
        other_replacements,
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
            "Notification sent successfully",
            url=notification.url,
            response=resp,
        )
        return resp
    except Exception as e:
        logger.error(
            "Failed to send notification",
            url=notification.url,
            body=body,
            error=str(e),
        )
        raise


async def send_all_notifications(
    event_type: EventEnum,
    requester: User | None = None,
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
            succ = await send_notification(
                session=session,
                notification=notification,
                requester=requester,
                book_asin=book_asin,
                other_replacements=other_replacements,
            )
            if succ:
                logger.info(
                    "Notification sent successfully",
                    url=notification.url,
                    asin=book_asin,
                )
            else:
                logger.error(
                    "Failed to send notification",
                    url=notification.url,
                    asin=book_asin,
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
            requester,
            book.title,
            book_authors,
            book_narrators,
            notification.event.value,
            other_replacements,
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
        logger.error("Failed to send notification", error=str(e))
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
            succ = await send_manual_notification(
                notification=notif,
                book=book_request,
                requester=user,
                other_replacements=other_replacements,
            )
            if succ:
                logger.info("Manual notification sent successfully", url=notif.url)
            else:
                logger.error("Failed to send manual notification", url=notif.url)