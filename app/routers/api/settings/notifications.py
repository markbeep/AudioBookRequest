import json
import uuid
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Response, Security
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.internal.auth.authentication import AnyAuth, DetailedUser
from app.internal.models import (
    EventEnum,
    GroupEnum,
    Notification,
    NotificationBodyTypeEnum,
)
from app.internal.notifications import send_notification
from app.util.db import get_session

router = APIRouter(prefix="/notifications", tags=["Notifications"])


class NotificationRequest(BaseModel):
    id: uuid.UUID | None = None
    name: str = Field(min_length=1)
    url: str = Field(min_length=1)
    event_type: str
    body: str
    body_type: NotificationBodyTypeEnum
    headers: str = "{}"


@router.get("", response_model=list[Notification])
def list_notifications(
    session: Annotated[Session, Depends(get_session)],
    _: Annotated[DetailedUser, Security(AnyAuth(GroupEnum.admin))],
):
    return session.exec(select(Notification)).all()


def _validate_headers(headers: str) -> dict[str, str]:
    try:
        headers_json = json.loads(headers or "{}")  # pyright: ignore[reportAny]
        if not isinstance(headers_json, dict) or any(
            not isinstance(v, str)
            for v in cast(dict[str, object], headers_json).values()
        ):
            raise HTTPException(400, "Invalid headers JSON. Not of type object/dict")
        headers_json = cast(dict[str, str], headers_json)
        return headers_json
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(400, "Invalid headers JSON")


def _upsert_notification(
    name: str,
    url: str,
    event_type: str,
    body: str,
    body_type: NotificationBodyTypeEnum,
    headers: str,
    session: Session,
    notification_id: uuid.UUID | None = None,
):
    headers_json = _validate_headers(headers)
    try:
        if body_type == NotificationBodyTypeEnum.json:
            json_body = json.loads(body, strict=False)  # pyright: ignore[reportAny]
            if not isinstance(json_body, dict):
                raise HTTPException(422, "Invalid body. Not a JSON object")
            body = json.dumps(json_body, indent=2)
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(422, "Body is invalid JSON")

    try:
        event_enum = EventEnum(event_type)
    except ValueError:
        raise HTTPException(400, "Invalid event type")

    try:
        body_enum = NotificationBodyTypeEnum(body_type)
    except ValueError:
        raise HTTPException(400, "Invalid notification service type")

    if notification_id:
        notification = session.get(Notification, notification_id)
        if not notification:
            raise HTTPException(404, "Notification not found")
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
    session.refresh(notification)

    return notification


@router.post("", response_model=Notification)
def create_notification(
    body: NotificationRequest,
    session: Annotated[Session, Depends(get_session)],
    _: Annotated[DetailedUser, Security(AnyAuth(GroupEnum.admin))],
):
    return _upsert_notification(
        notification_id=body.id,
        name=body.name,
        url=body.url,
        event_type=body.event_type,
        body=body.body,
        body_type=body.body_type,
        headers=body.headers,
        session=session,
    )


@router.delete("/{id}")
def delete_notification(
    id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    _: Annotated[DetailedUser, Security(AnyAuth(GroupEnum.admin))],
):
    notif = session.get(Notification, id)
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")

    session.delete(notif)
    session.commit()
    return Response(status_code=204)


@router.post("/{id}/test")
async def test_notification_id(
    id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    _: Annotated[DetailedUser, Security(AnyAuth(GroupEnum.admin))],
):
    notif = session.get(Notification, id)
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")

    try:
        await send_notification(session, notif)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    return Response(status_code=200)


@router.patch("/{id}/enable")
def toggle_notification(
    id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    _: Annotated[DetailedUser, Security(AnyAuth(GroupEnum.admin))],
):
    notif = session.get(Notification, id)
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")

    notif.enabled = not notif.enabled
    session.add(notif)
    session.commit()
    session.refresh(notif)
    return notif


@router.post("/test")
async def test_notification(
    body: NotificationRequest,
    session: Annotated[Session, Depends(get_session)],
    _: Annotated[DetailedUser, Security(AnyAuth(GroupEnum.admin))],
):
    headers_json = _validate_headers(body.headers)
    try:
        event_enum = EventEnum(body.event_type)
    except ValueError:
        raise HTTPException(400, "Invalid event type")
    try:
        await send_notification(
            session,
            Notification(
                name=body.name,
                url=body.url,
                event=event_enum,
                body=body.body,
                body_type=body.body_type,
                headers=headers_json,
                enabled=True,
            ),
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    return Response(status_code=200)
