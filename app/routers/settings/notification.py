import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, Security
from sqlmodel import Session

from app.internal.auth.authentication import ABRAuth, DetailedUser
from app.internal.models import (
    EventEnum,
    GroupEnum,
    NotificationBodyTypeEnum,
)
from app.routers.api.settings.notifications import (
    NotificationRequest,
    list_notifications,
)
from app.routers.api.settings.notifications import (
    create_notification as api_create_notification,
)
from app.routers.api.settings.notifications import (
    delete_notification as api_delete_notification,
)
from app.routers.api.settings.notifications import (
    test_notification_id as api_test_notification_id,
)
from app.routers.api.settings.notifications import (
    toggle_notification as api_toggle_notification,
)
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
    notifications = list_notifications(session, admin_user)
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
    notifications = list_notifications(session, admin_user)
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


@router.post("")
def add_notification(
    request: Request,
    name: Annotated[str, Form()],
    url: Annotated[str, Form()],
    event_type: Annotated[str, Form()],
    body_type: Annotated[NotificationBodyTypeEnum, Form()],
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
    headers: Annotated[str, Form()] = "{}",
    body: Annotated[str, Form()] = "{}",
):
    try:
        api_create_notification(
            NotificationRequest(
                id=None,
                name=name,
                url=url,
                event_type=event_type,
                body=body,
                body_type=body_type,
                headers=headers,
            ),
            session,
            admin_user,
        )
    except HTTPException as e:
        raise ToastException(e.detail, "error")
    return _list_notifications(request, session, admin_user)


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
    try:
        api_create_notification(
            NotificationRequest(
                id=notification_id,
                name=name,
                url=url,
                event_type=event_type,
                body=body,
                body_type=body_type,
                headers=headers,
            ),
            session,
            admin_user,
        )
    except HTTPException as e:
        raise ToastException(e.detail, "error")
    return _list_notifications(request, session, admin_user)


@router.patch("/{notification_id}/enable")
def toggle_notification(
    request: Request,
    notification_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    try:
        api_toggle_notification(notification_id, session, admin_user)
    except HTTPException as e:
        raise ToastException(e.detail, "error")

    return _list_notifications(request, session, admin_user)


@router.delete("/{notification_id}")
def delete_notification(
    request: Request,
    notification_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    try:
        api_delete_notification(notification_id, session, admin_user)
    except HTTPException as e:
        raise ToastException(e.detail, "error")

    return _list_notifications(request, session, admin_user)


@router.post("/{notification_id}")
async def test_notification(
    notification_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    try:
        await api_test_notification_id(notification_id, session, admin_user)
    except HTTPException as e:
        raise ToastException(e.detail, "error") from None

    return Response(status_code=204)
