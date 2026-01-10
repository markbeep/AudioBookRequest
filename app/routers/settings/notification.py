import json
import uuid
from typing import Annotated, Optional, cast

from aiohttp import ClientResponseError
from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, Security
from sqlmodel import Session, select

from app.internal.auth.authentication import ABRAuth, DetailedUser
from app.internal.models import (
    EventEnum,
    GroupEnum,
    Notification,
    NotificationBodyTypeEnum,
)
from app.internal.notifications import send_notification
from app.util.db import get_session
from app.util.templates import template_response
from app.util.toast import ToastException

router = APIRouter(prefix="/notifications")


@router.get("")
def read_notifications(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    notifications = session.exec(select(Notification)).all()
    event_types = [e.value for e in EventEnum]
    body_types = [e.value for e in NotificationBodyTypeEnum]
    return template_response(
        "settings_page/notifications.html",
        request,
        admin_user,
        {
            "page": "notifications",
            "notifications": notifications,
            "event_types": event_types,
            "body_types": body_types,
        },
    )


def _list_notifications(request: Request, session: Session, admin_user: DetailedUser):
    notifications = session.exec(select(Notification)).all()
    event_types = [e.value for e in EventEnum]
    body_types = [e.value for e in NotificationBodyTypeEnum]
    return template_response(
        "settings_page/notifications.html",
        request,
        admin_user,
        {
            "page": "notifications",
            "notifications": notifications,
            "event_types": event_types,
            "body_types": body_types,
        },
        block_name="notfications_block",
    )


def _upsert_notification(
    request: Request,
    *,
    name: str,
    url: str,
    event_type: str,
    body: str,
    body_type: NotificationBodyTypeEnum,
    headers: str,
    admin_user: DetailedUser,
    session: Session,
    notification_id: Optional[uuid.UUID] = None,
):
    try:
        headers_json = json.loads(headers or "{}")  # pyright: ignore[reportAny]
        if not isinstance(headers_json, dict) or any(
            not isinstance(v, str)
            for v in cast(dict[str, object], headers_json).values()
        ):
            raise ToastException(
                "Invalid headers JSON. Not of type object/dict", "error"
            )
        headers_json = cast(dict[str, str], headers_json)
    except (json.JSONDecodeError, ValueError):
        raise ToastException("Invalid headers JSON", "error")

    try:
        if body_type == NotificationBodyTypeEnum.json:
            json_body = json.loads(body, strict=False)  # pyright: ignore[reportAny]
            if not isinstance(json_body, dict):
                raise ToastException("Invalid body. Not a JSON object", "error")
            body = json.dumps(json_body, indent=2)
    except (json.JSONDecodeError, ValueError):
        raise ToastException("Body is invalid JSON", "error")

    try:
        event_enum = EventEnum(event_type)
    except ValueError:
        raise ToastException("Invalid event type", "error")

    try:
        body_enum = NotificationBodyTypeEnum(body_type)
    except ValueError:
        raise ToastException("Invalid notification service type", "error")

    if notification_id:
        notification = session.get(Notification, notification_id)
        if not notification:
            raise ToastException("Notification not found", "error")
        notification.name = name
        notification.url = url
        notification.event = event_enum
        notification.body_type = body_enum
        notification.body = body
        notification.headers = headers_json
        notification.enabled = True
    else:
        notification = Notification(
            name=name,
            url=url,
            event=event_enum,
            body_type=body_enum,
            body=body,
            headers=headers_json,
            enabled=True,
        )
    session.add(notification)
    session.commit()

    return _list_notifications(request, session, admin_user)


@router.post("")
def add_notification(
    request: Request,
    name: Annotated[str, Form()],
    url: Annotated[str, Form()],
    event_type: Annotated[str, Form()],
    body_type: Annotated[NotificationBodyTypeEnum, Form()],
    headers: Annotated[str, Form()],
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
    body: Annotated[str, Form()] = "{}",
):
    return _upsert_notification(
        request=request,
        name=name,
        url=url,
        event_type=event_type,
        body=body,
        body_type=body_type,
        headers=headers,
        admin_user=admin_user,
        session=session,
    )


@router.put("/{notification_id}")
def update_notification(
    request: Request,
    notification_id: uuid.UUID,
    name: Annotated[str, Form()],
    url: Annotated[str, Form()],
    event_type: Annotated[str, Form()],
    body_type: Annotated[NotificationBodyTypeEnum, Form()],
    headers: Annotated[str, Form()],
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
    body: Annotated[str, Form()] = "{}",
):
    return _upsert_notification(
        notification_id=notification_id,
        request=request,
        name=name,
        url=url,
        event_type=event_type,
        body=body,
        body_type=body_type,
        headers=headers,
        admin_user=admin_user,
        session=session,
    )


@router.patch("/{notification_id}/enable")
def toggle_notification(
    request: Request,
    notification_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    notification = session.get_one(Notification, notification_id)
    if not notification:
        raise ToastException("Notification not found", "error")
    notification.enabled = not notification.enabled
    session.add(notification)
    session.commit()

    return _list_notifications(request, session, admin_user)


@router.delete("/{notification_id}")
def delete_notification(
    request: Request,
    notification_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    notification = session.get_one(Notification, notification_id)
    if not notification:
        raise ToastException("Notification not found", "error")
    session.delete(notification)
    session.commit()

    return _list_notifications(request, session, admin_user)


@router.post("/{notification_id}")
async def test_notification(
    notification_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    _ = admin_user
    notification = session.get(Notification, notification_id)
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    try:
        await send_notification(session, notification)
    except ClientResponseError:
        raise HTTPException(status_code=500, detail="Failed to send notification")

    return Response(status_code=204)
