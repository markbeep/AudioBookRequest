import json
import uuid
from typing import Annotated, Any, Optional, cast

from aiohttp import ClientResponseError, ClientSession
from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from sqlmodel import Session, select

from app.internal.models import EventEnum, GroupEnum, Notification, User
from app.internal.prowlarr.indexer_categories import indexer_categories
from app.internal.notifications import send_notification
from app.internal.prowlarr.prowlarr import flush_prowlarr_cache, prowlarr_config
from app.internal.indexers.mam import mam_config

from app.internal.ranking.quality import IndexerFlag, QualityRange, quality_config
from app.util.auth import (
    DetailedUser,
    LoginTypeEnum,
    auth_config,
    create_user,
    get_authenticated_user,
    is_correct_password,
    raise_for_invalid_password,
)
from app.util.connection import get_connection
from app.util.db import get_session
from app.util.templates import template_response

router = APIRouter(prefix="/settings")


@router.get("/account")
def read_account(
    request: Request,
    user: Annotated[DetailedUser, Depends(get_authenticated_user())],
):
    return template_response(
        "settings_page/account.html", request, user, {"page": "account"}
    )


@router.post("/account/password")
def change_password(
    request: Request,
    old_password: Annotated[str, Form()],
    password: Annotated[str, Form()],
    confirm_password: Annotated[str, Form()],
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Depends(get_authenticated_user())],
):
    if not is_correct_password(user, old_password):
        return template_response(
            "settings_page/account.html",
            request,
            user,
            {"page": "account", "error": "Old password is incorrect"},
            block_name="error",
            headers={"HX-Retarget": "#error"},
        )
    try:
        raise_for_invalid_password(session, password, confirm_password)
    except HTTPException as e:
        return template_response(
            "settings_page/account.html",
            request,
            user,
            {"page": "account", "error": e.detail},
            block_name="error",
            headers={"HX-Retarget": "#error"},
        )

    new_user = create_user(user.username, password, user.group)
    old_user = session.exec(select(User).where(User.username == user.username)).one()
    old_user.password = new_user.password
    session.add(old_user)
    session.commit()

    return template_response(
        "settings_page/account.html",
        request,
        user,
        {"page": "account", "success": "Password changed"},
        block_name="content",
    )


@router.get("/users")
def read_users(
    request: Request,
    admin_user: Annotated[
        DetailedUser, Depends(get_authenticated_user(GroupEnum.admin))
    ],
    session: Annotated[Session, Depends(get_session)],
):
    users = session.exec(select(User)).all()
    return template_response(
        "settings_page/users.html",
        request,
        admin_user,
        {"page": "users", "users": users},
    )


@router.post("/user")
def create_new_user(
    request: Request,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    group: Annotated[str, Form()],
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[
        DetailedUser, Depends(get_authenticated_user(GroupEnum.admin))
    ],
):
    if username.strip() == "":
        return template_response(
            "settings_page/users.html",
            request,
            admin_user,
            {"error": "Invalid username"},
            block_name="toast_block",
            headers={"HX-Retarget": "#toast-block"},
        )

    try:
        raise_for_invalid_password(session, password, ignore_confirm=True)
    except HTTPException as e:
        return template_response(
            "settings_page/users.html",
            request,
            admin_user,
            {"error": e.detail},
            block_name="toast_block",
            headers={"HX-Retarget": "#toast-block"},
        )

    if group not in GroupEnum.__members__:
        return template_response(
            "settings_page/users.html",
            request,
            admin_user,
            {"error": "Invalid group selected"},
            block_name="toast_block",
            headers={"HX-Retarget": "#toast-block"},
        )

    group = GroupEnum[group]

    user = session.exec(select(User).where(User.username == username)).first()
    if user:
        return template_response(
            "settings_page/users.html",
            request,
            admin_user,
            {"error": "Username already exists"},
            block_name="toast_block",
            headers={"HX-Retarget": "#toast-block"},
        )

    user = create_user(username, password, group)
    session.add(user)
    session.commit()

    users = session.exec(select(User)).all()

    return template_response(
        "settings_page/users.html",
        request,
        admin_user,
        {"users": users, "success": "Created user"},
        block_name="user_block",
    )


@router.delete("/user/{username}")
def delete_user(
    request: Request,
    username: str,
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[
        DetailedUser, Depends(get_authenticated_user(GroupEnum.admin))
    ],
):
    if username == admin_user.username:
        users = session.exec(select(User)).all()
        return template_response(
            "settings_page/users.html",
            request,
            admin_user,
            {"error": "Cannot delete own user"},
            block_name="toast_block",
            headers={"HX-Retarget": "#toast-block"},
        )

    user = session.exec(select(User).where(User.username == username)).one_or_none()
    if user and user.root:
        return template_response(
            "settings_page/users.html",
            request,
            admin_user,
            {"error": "Cannot delete root user"},
            block_name="toast_block",
            headers={"HX-Retarget": "#toast-block"},
        )

    if user:
        session.delete(user)
        session.commit()

    users = session.exec(select(User)).all()

    return template_response(
        "settings_page/users.html",
        request,
        admin_user,
        {"users": users, "success": "Deleted user"},
        block_name="user_block",
    )


@router.patch("/user/{username}")
def update_user(
    request: Request,
    username: str,
    group: Annotated[GroupEnum, Form()],
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[
        DetailedUser, Depends(get_authenticated_user(GroupEnum.admin))
    ],
):
    user = session.exec(select(User).where(User.username == username)).one_or_none()
    if user and user.root:
        return template_response(
            "settings_page/users.html",
            request,
            admin_user,
            {"error": "Cannot change root user"},
            block_name="toast_block",
            headers={"HX-Retarget": "#toast-block"},
        )

    if user:
        user.group = group
        session.add(user)
        session.commit()

    users = session.exec(select(User)).all()
    return template_response(
        "settings_page/users.html",
        request,
        admin_user,
        {"users": users, "success": "Updated user"},
        block_name="user_block",
    )


@router.get("/prowlarr")
def read_prowlarr(
    request: Request,
    admin_user: Annotated[
        DetailedUser, Depends(get_authenticated_user(GroupEnum.admin))
    ],
    session: Annotated[Session, Depends(get_session)],
    prowlarr_misconfigured: Optional[Any] = None,
):
    prowlarr_base_url = prowlarr_config.get_base_url(session)
    prowlarr_api_key = prowlarr_config.get_api_key(session)
    selected = set(prowlarr_config.get_categories(session))
    mam_is_active = mam_config.is_active(session)
    mam_id = mam_config.get_session_id(session)

    return template_response(
        "settings_page/prowlarr.html",
        request,
        admin_user,
        {
            "page": "prowlarr",
            "prowlarr_base_url": prowlarr_base_url or "",
            "prowlarr_api_key": prowlarr_api_key,
            "indexer_categories": indexer_categories,
            "selected_categories": selected,
            "prowlarr_misconfigured": True if prowlarr_misconfigured else False,
            "mam_active": mam_is_active,
            "mam_id": mam_id,
        },
    )


@router.put("/prowlarr/api-key")
def update_prowlarr_api_key(
    api_key: Annotated[str, Form()],
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[
        DetailedUser, Depends(get_authenticated_user(GroupEnum.admin))
    ],
):
    prowlarr_config.set_api_key(session, api_key)
    return Response(status_code=204, headers={"HX-Refresh": "true"})


@router.put("/prowlarr/base-url")
def update_prowlarr_base_url(
    base_url: Annotated[str, Form()],
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[
        DetailedUser, Depends(get_authenticated_user(GroupEnum.admin))
    ],
):
    prowlarr_config.set_base_url(session, base_url)
    return Response(status_code=204, headers={"HX-Refresh": "true"})


@router.put("/prowlarr/category")
def update_indexer_categories(
    request: Request,
    admin_user: Annotated[
        DetailedUser, Depends(get_authenticated_user(GroupEnum.admin))
    ],
    session: Annotated[Session, Depends(get_session)],
    categories: Annotated[list[int], Form(alias="c")] = [],
):
    prowlarr_config.set_categories(session, categories)
    selected = set(categories)
    flush_prowlarr_cache()

    return template_response(
        "settings_page/prowlarr.html",
        request,
        admin_user,
        {
            "indexer_categories": indexer_categories,
            "selected_categories": selected,
            "success": "Categories updated",
        },
        block_name="category",
    )


@router.put("/mam/mam_id")
def update_mam_id(
    mam_id: Annotated[str, Form()],
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[
        DetailedUser, Depends(get_authenticated_user(GroupEnum.admin))
    ],
):
    mam_config.set_mam_id(session, mam_id)
    return Response(status_code=204, headers={"HX-Refresh": "true"})


@router.put("/mam/activate")
def activate_mam(
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[
        DetailedUser, Depends(get_authenticated_user(GroupEnum.admin))
    ],
):
    mam_config.set_active(session, True)
    return Response(status_code=204, headers={"HX-Refresh": "true"})


@router.put("/mam/deactivate")
def deactivate_mam(
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[
        DetailedUser, Depends(get_authenticated_user(GroupEnum.admin))
    ],
):
    mam_config.set_active(session, False)
    return Response(status_code=204, headers={"HX-Refresh": "true"})


@router.get("/download")
def read_download(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[
        DetailedUser, Depends(get_authenticated_user(GroupEnum.admin))
    ],
):
    auto_download = quality_config.get_auto_download(session)
    flac_range = quality_config.get_range(session, "quality_flac")
    m4b_range = quality_config.get_range(session, "quality_m4b")
    mp3_range = quality_config.get_range(session, "quality_mp3")
    unknown_audio_range = quality_config.get_range(session, "quality_unknown_audio")
    unknown_range = quality_config.get_range(session, "quality_unknown")
    min_seeders = quality_config.get_min_seeders(session)
    name_ratio = quality_config.get_name_exists_ratio(session)
    title_ratio = quality_config.get_title_exists_ratio(session)
    flags = quality_config.get_indexer_flags(session)

    return template_response(
        "settings_page/download.html",
        request,
        admin_user,
        {
            "page": "download",
            "auto_download": auto_download,
            "flac_range": flac_range,
            "m4b_range": m4b_range,
            "mp3_range": mp3_range,
            "unknown_audio_range": unknown_audio_range,
            "unknown_range": unknown_range,
            "min_seeders": min_seeders,
            "name_ratio": name_ratio,
            "title_ratio": title_ratio,
            "indexer_flags": flags,
        },
    )


@router.post("/download")
def update_download(
    request: Request,
    flac_from: Annotated[float, Form()],
    flac_to: Annotated[float, Form()],
    m4b_from: Annotated[float, Form()],
    m4b_to: Annotated[float, Form()],
    mp3_from: Annotated[float, Form()],
    mp3_to: Annotated[float, Form()],
    unknown_audio_from: Annotated[float, Form()],
    unknown_audio_to: Annotated[float, Form()],
    unknown_from: Annotated[float, Form()],
    unknown_to: Annotated[float, Form()],
    min_seeders: Annotated[int, Form()],
    name_ratio: Annotated[int, Form()],
    title_ratio: Annotated[int, Form()],
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[
        DetailedUser, Depends(get_authenticated_user(GroupEnum.admin))
    ],
    auto_download: Annotated[bool, Form()] = False,
):
    flac = QualityRange(from_kbits=flac_from, to_kbits=flac_to)
    m4b = QualityRange(from_kbits=m4b_from, to_kbits=m4b_to)
    mp3 = QualityRange(from_kbits=mp3_from, to_kbits=mp3_to)
    unknown_audio = QualityRange(
        from_kbits=unknown_audio_from, to_kbits=unknown_audio_to
    )
    unknown = QualityRange(from_kbits=unknown_from, to_kbits=unknown_to)

    quality_config.set_auto_download(session, auto_download)
    quality_config.set_range(session, "quality_flac", flac)
    quality_config.set_range(session, "quality_m4b", m4b)
    quality_config.set_range(session, "quality_mp3", mp3)
    quality_config.set_range(session, "quality_unknown_audio", unknown_audio)
    quality_config.set_range(session, "quality_unknown", unknown)
    quality_config.set_min_seeders(session, min_seeders)
    quality_config.set_name_exists_ratio(session, name_ratio)
    quality_config.set_title_exists_ratio(session, title_ratio)

    return template_response(
        "settings_page/download.html",
        request,
        admin_user,
        {
            "page": "download",
            "success": "Settings updated",
            "auto_download": auto_download,
            "flac_range": flac,
            "m4b_range": m4b,
            "mp3_range": mp3,
            "unknown_audio_range": unknown_audio,
            "unknown_range": unknown,
            "min_seeders": min_seeders,
            "name_ratio": name_ratio,
            "title_ratio": title_ratio,
        },
        block_name="form",
    )


@router.delete("/download")
def reset_download_setings(
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[
        DetailedUser, Depends(get_authenticated_user(GroupEnum.admin))
    ],
):
    quality_config.reset_all(session)
    return Response(status_code=204, headers={"HX-Refresh": "true"})


@router.post("/download/indexer-flag")
def add_indexer_flag(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[
        DetailedUser, Depends(get_authenticated_user(GroupEnum.admin))
    ],
    flag: Annotated[str, Form()],
    score: Annotated[int, Form()],
):
    flags = quality_config.get_indexer_flags(session)
    if not any(f.flag == flag for f in flags):
        flags.append(IndexerFlag(flag=flag.lower(), score=score))
        quality_config.set_indexer_flags(session, flags)

    return template_response(
        "settings_page/download.html",
        request,
        admin_user,
        {"page": "download", "indexer_flags": flags},
        block_name="flags",
    )


@router.delete("/download/indexer-flag/{flag}")
def remove_indexer_flag(
    request: Request,
    flag: str,
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[
        DetailedUser, Depends(get_authenticated_user(GroupEnum.admin))
    ],
):
    # TODO: very bad concurrency here
    flags = quality_config.get_indexer_flags(session)
    flags = [f for f in flags if f.flag != flag]
    quality_config.set_indexer_flags(session, flags)
    return template_response(
        "settings_page/download.html",
        request,
        admin_user,
        {"page": "download", "indexer_flags": flags},
        block_name="flags",
    )


@router.get("/notifications")
def read_notifications(
    request: Request,
    admin_user: Annotated[
        DetailedUser, Depends(get_authenticated_user(GroupEnum.admin))
    ],
    session: Annotated[Session, Depends(get_session)],
):
    notifications = session.exec(select(Notification)).all()
    event_types = [e.value for e in EventEnum]
    return template_response(
        "settings_page/notifications.html",
        request,
        admin_user,
        {
            "page": "notifications",
            "notifications": notifications,
            "event_types": event_types,
        },
    )


@router.post("/notification")
def add_notification(
    request: Request,
    name: Annotated[str, Form()],
    apprise_url: Annotated[str, Form()],
    title_template: Annotated[str, Form()],
    body_template: Annotated[str, Form()],
    event_type: Annotated[str, Form()],
    headers: Annotated[str, Form()],
    admin_user: Annotated[
        DetailedUser, Depends(get_authenticated_user(GroupEnum.admin))
    ],
    session: Annotated[Session, Depends(get_session)],
):
    if not headers:
        headers = "{}"
    try:
        headers_json = json.loads(headers)
        if not isinstance(headers_json, dict) or any(
            not isinstance(v, str) for v in cast(dict[str, Any], headers_json).values()
        ):
            raise ValueError()
        headers_json = cast(dict[str, str], headers_json)
    except (json.JSONDecodeError, ValueError):
        return template_response(
            "settings_page/notifications.html",
            request,
            admin_user,
            {"page": "notifications", "error": "Invalid headers JSON"},
            block_name="form_error",
        )

    try:
        event_enum = EventEnum(event_type)
    except ValueError:
        return template_response(
            "settings_page/notifications.html",
            request,
            admin_user,
            {"page": "notifications", "error": "Invalid event type"},
            block_name="form_error",
        )

    notification = Notification(
        name=name,
        apprise_url=apprise_url,
        event=event_enum,
        title_template=title_template,
        body_template=body_template,
        headers=headers_json,
        enabled=True,
    )
    session.add(notification)
    session.commit()

    notifications = session.exec(select(Notification)).all()

    return template_response(
        "settings_page/notifications.html",
        request,
        admin_user,
        {"page": "notifications", "notifications": notifications},
        block_name="notfications_block",
        headers={"HX-Retarget": "#notification-list"},
    )


@router.delete("/notification/{notification_id}")
def delete_notification(
    request: Request,
    notification_id: uuid.UUID,
    admin_user: Annotated[
        DetailedUser, Depends(get_authenticated_user(GroupEnum.admin))
    ],
    session: Annotated[Session, Depends(get_session)],
):
    notifications = session.exec(select(Notification)).all()
    for notif in notifications:
        if notif.id == notification_id:
            session.delete(notif)
            session.commit()
            break
    notifications = session.exec(select(Notification)).all()

    return template_response(
        "settings_page/notifications.html",
        request,
        admin_user,
        {"page": "notifications", "notifications": notifications},
        block_name="notfications_block",
    )


@router.post("/notification/{notification_id}")
async def execute_notification(
    notification_id: uuid.UUID,
    admin_user: Annotated[
        DetailedUser, Depends(get_authenticated_user(GroupEnum.admin))
    ],
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
):
    notification = session.exec(
        select(Notification).where(Notification.id == notification_id)
    ).one_or_none()
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    try:
        await send_notification(session, notification)
    except ClientResponseError:
        raise HTTPException(status_code=500, detail="Failed to send notification")

    return Response(status_code=204)


@router.get("/security")
def read_security(
    request: Request,
    admin_user: Annotated[
        DetailedUser, Depends(get_authenticated_user(GroupEnum.admin))
    ],
    session: Annotated[Session, Depends(get_session)],
):
    return template_response(
        "settings_page/security.html",
        request,
        admin_user,
        {
            "page": "security",
            "login_type": auth_config.get_login_type(session),
            "access_token_expiry": auth_config.get_access_token_expiry_minutes(session),
            "min_password_length": auth_config.get_min_password_length(session),
        },
    )


@router.post("/security/reset-auth")
def reset_auth_secret(
    admin_user: Annotated[
        DetailedUser, Depends(get_authenticated_user(GroupEnum.admin))
    ],
    session: Annotated[Session, Depends(get_session)],
):
    auth_config.reset_auth_secret(session)
    return Response(status_code=204, headers={"HX-Refresh": "true"})


@router.post("/security")
def update_security(
    login_type: Annotated[LoginTypeEnum, Form()],
    access_token_expiry: Annotated[int, Form()],
    min_password_length: Annotated[int, Form()],
    request: Request,
    admin_user: Annotated[
        DetailedUser, Depends(get_authenticated_user(GroupEnum.admin))
    ],
    session: Annotated[Session, Depends(get_session)],
):
    if access_token_expiry < 1:
        return template_response(
            "settings_page/security.html",
            request,
            admin_user,
            {"error": "Access token expiry can't be 0 or negative"},
            block_name="error_toast",
            headers={"HX-Retarget": "#message"},
        )

    if min_password_length < 1:
        return template_response(
            "settings_page/security.html",
            request,
            admin_user,
            {"error": "Minimum password length can't be 0 or negative"},
            block_name="error_toast",
            headers={"HX-Retarget": "#message"},
        )

    old = auth_config.get_login_type(session)
    auth_config.set_login_type(session, login_type)
    auth_config.set_access_token_expiry_minutes(session, access_token_expiry)
    auth_config.set_min_password_length(session, min_password_length)
    return template_response(
        "settings_page/security.html",
        request,
        admin_user,
        {
            "page": "security",
            "login_type": auth_config.get_login_type(session),
            "access_token_expiry": auth_config.get_access_token_expiry_minutes(session),
            "success": "Settings updated",
        },
        block_name="form",
        headers={} if old == login_type else {"HX-Refresh": "true"},
    )
