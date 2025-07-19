import json
import uuid
from typing import Annotated, Any, Optional, cast

from aiohttp import ClientResponseError, ClientSession
from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from sqlmodel import Session, select

from app.internal.auth.authentication import (
    DetailedUser,
    create_api_key,
    create_user,
    get_authenticated_user,
    is_correct_password,
    raise_for_invalid_password,
)
from app.internal.auth.config import LoginTypeEnum, auth_config
from app.internal.auth.oidc_config import oidc_config
from app.internal.env_settings import Settings
from app.internal.indexers.abstract import SessionContainer
from app.internal.indexers.configuration import indexer_configuration_cache
from app.internal.indexers.indexer_util import IndexerContext, get_indexer_contexts
from app.internal.models import (
    APIKey,
    NotificationBodyTypeEnum,
    EventEnum,
    GroupEnum,
    Notification,
    User,
)
from app.internal.notifications import send_notification
from app.internal.prowlarr.indexer_categories import indexer_categories
from app.internal.prowlarr.prowlarr import (
    flush_prowlarr_cache,
    get_indexers,
    prowlarr_config,
)
from app.internal.ranking.quality import IndexerFlag, QualityRange, quality_config
from app.util.connection import get_connection
from app.util.db import get_session
from app.util.log import logger
from app.util.templates import template_response
from app.util.time import Minute
from app.util.toast import ToastException

router = APIRouter(prefix="/settings")


@router.get("/account")
def read_account(
    request: Request,
    user: Annotated[DetailedUser, Depends(get_authenticated_user())],
    session: Annotated[Session, Depends(get_session)],
):
    api_keys = session.exec(select(APIKey).where(APIKey.user_username == user.username)).all()
    return template_response(
        "settings_page/account.html",
        request,
        user,
        {"page": "account", "version": Settings().app.version, "api_keys": api_keys},
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
        raise ToastException("Old password is incorrect", "error")
    try:
        raise_for_invalid_password(session, password, confirm_password)
    except HTTPException as e:
        raise ToastException(e.detail, "error")

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


@router.post("/account/api-key")
def create_new_api_key(
    request: Request,
    name: Annotated[str, Form()],
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Depends(get_authenticated_user())],
):
    if not name.strip():
        raise ToastException("API key name cannot be empty", "error")
    
    api_key, key = create_api_key(session, user, name.strip())
    
    api_keys = session.exec(select(APIKey).where(APIKey.user_username == user.username)).all()
    
    return template_response(
        "settings_page/account.html",
        request,
        user,
        {
            "page": "account", 
            "api_keys": api_keys,
            "success": f"API key created: {key}",
            "show_api_key": True,
            "new_api_key": key,
        },
        block_name="api_keys",
    )


@router.delete("/account/api-key/{api_key_id}")
def delete_api_key(
    request: Request,
    api_key_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Depends(get_authenticated_user())],
):
    api_key = session.exec(
        select(APIKey).where(
            APIKey.id == api_key_id,
            APIKey.user_username == user.username
        )
    ).first()
    
    if not api_key:
        raise ToastException("API key not found", "error")
    
    session.delete(api_key)
    session.commit()
    
    api_keys = session.exec(select(APIKey).where(APIKey.user_username == user.username)).all()
    return template_response(
        "settings_page/account.html",
        request,
        user,
        {
            "page": "account",
            "api_keys": api_keys,
            "success": "API key deleted",
        },
        block_name="api_keys",
    )


@router.patch("/account/api-key/{api_key_id}/toggle")
def toggle_api_key(
    request: Request,
    api_key_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Depends(get_authenticated_user())],
):
    api_key = session.exec(
        select(APIKey).where(
            APIKey.id == api_key_id,
            APIKey.user_username == user.username
        )
    ).first()
    
    if not api_key:
        raise ToastException("API key not found", "error")
    
    api_key.enabled = not api_key.enabled
    session.add(api_key)
    session.commit()
    
    api_keys = session.exec(select(APIKey).where(APIKey.user_username == user.username)).all()
    return template_response(
        "settings_page/account.html",
        request,
        user,
        {
            "page": "account",
            "api_keys": api_keys,
            "success": f"API key {'enabled' if api_key.enabled else 'disabled'}",
        },
        block_name="api_keys",
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
    is_oidc = auth_config.get_login_type(session) == LoginTypeEnum.oidc
    return template_response(
        "settings_page/users.html",
        request,
        admin_user,
        {
            "page": "users",
            "users": users,
            "is_oidc": is_oidc,
        },
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
        raise ToastException("Invalid username", "error")

    try:
        raise_for_invalid_password(session, password, ignore_confirm=True)
    except HTTPException as e:
        raise ToastException(e.detail, "error")

    if group not in GroupEnum.__members__:
        raise ToastException("Invalid group selected", "error")

    group = GroupEnum[group]

    user = session.exec(select(User).where(User.username == username)).first()
    if user:
        raise ToastException("Username already exists", "error")

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
        raise ToastException("Cannot delete own user", "error")

    user = session.exec(select(User).where(User.username == username)).one_or_none()
    if user and user.root:
        raise ToastException("Cannot delete root user", "error")

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
        raise ToastException("Cannot change root user's group", "error")

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
async def read_prowlarr(
    request: Request,
    admin_user: Annotated[
        DetailedUser, Depends(get_authenticated_user(GroupEnum.admin))
    ],
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    prowlarr_misconfigured: Optional[Any] = None,
):
    prowlarr_base_url = prowlarr_config.get_base_url(session)
    prowlarr_api_key = prowlarr_config.get_api_key(session)
    selected = set(prowlarr_config.get_categories(session))
    indexers = await get_indexers(session, client_session)
    selected_indexers = set(prowlarr_config.get_indexers(session))

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
            "indexers": indexers,
            "selected_indexers": selected_indexers,
            "prowlarr_misconfigured": True if prowlarr_misconfigured else False,
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
    flush_prowlarr_cache()
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
    flush_prowlarr_cache()
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


@router.put("/prowlarr/indexers")
async def update_selected_indexers(
    request: Request,
    admin_user: Annotated[
        DetailedUser, Depends(get_authenticated_user(GroupEnum.admin))
    ],
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    indexer_ids: Annotated[list[int], Form(alias="i")] = [],
):
    prowlarr_config.set_indexers(session, indexer_ids)

    indexers = await get_indexers(session, client_session)
    selected_indexers = set(prowlarr_config.get_indexers(session))
    flush_prowlarr_cache()

    return template_response(
        "settings_page/prowlarr.html",
        request,
        admin_user,
        {
            "indexers": indexers,
            "selected_indexers": selected_indexers,
            "success": "Indexers updated",
        },
        block_name="indexer",
    )


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
        headers_json = json.loads(headers or "{}")
        if not isinstance(headers_json, dict) or any(
            not isinstance(v, str) for v in cast(dict[str, Any], headers_json).values()
        ):
            raise ToastException(
                "Invalid headers JSON. Not of type object/dict", "error"
            )
        headers_json = cast(dict[str, str], headers_json)
    except (json.JSONDecodeError, ValueError):
        raise ToastException("Invalid headers JSON", "error")

    try:
        if body_type == NotificationBodyTypeEnum.json:
            json_body = json.loads(body, strict=False)
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


@router.post("/notification")
def add_notification(
    request: Request,
    name: Annotated[str, Form()],
    url: Annotated[str, Form()],
    event_type: Annotated[str, Form()],
    body_type: Annotated[NotificationBodyTypeEnum, Form()],
    headers: Annotated[str, Form()],
    admin_user: Annotated[
        DetailedUser, Depends(get_authenticated_user(GroupEnum.admin))
    ],
    session: Annotated[Session, Depends(get_session)],
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


@router.put("/notification/{notification_id}")
def update_notification(
    request: Request,
    notification_id: uuid.UUID,
    name: Annotated[str, Form()],
    url: Annotated[str, Form()],
    event_type: Annotated[str, Form()],
    body_type: Annotated[NotificationBodyTypeEnum, Form()],
    headers: Annotated[str, Form()],
    admin_user: Annotated[
        DetailedUser, Depends(get_authenticated_user(GroupEnum.admin))
    ],
    session: Annotated[Session, Depends(get_session)],
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


@router.patch("/notification/{notification_id}/enable")
def toggle_notification(
    request: Request,
    notification_id: uuid.UUID,
    admin_user: Annotated[
        DetailedUser, Depends(get_authenticated_user(GroupEnum.admin))
    ],
    session: Annotated[Session, Depends(get_session)],
):
    notification = session.get_one(Notification, notification_id)
    if not notification:
        raise ToastException("Notification not found", "error")
    notification.enabled = not notification.enabled
    session.add(notification)
    session.commit()

    return _list_notifications(request, session, admin_user)


@router.delete("/notification/{notification_id}")
def delete_notification(
    request: Request,
    notification_id: uuid.UUID,
    admin_user: Annotated[
        DetailedUser, Depends(get_authenticated_user(GroupEnum.admin))
    ],
    session: Annotated[Session, Depends(get_session)],
):
    notification = session.get_one(Notification, notification_id)
    if not notification:
        raise ToastException("Notification not found", "error")
    session.delete(notification)
    session.commit()

    return _list_notifications(request, session, admin_user)


@router.post("/notification/{notification_id}")
async def test_notification(
    notification_id: uuid.UUID,
    admin_user: Annotated[
        DetailedUser, Depends(get_authenticated_user(GroupEnum.admin))
    ],
    session: Annotated[Session, Depends(get_session)],
):
    notification = session.get(Notification, notification_id)
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
            "oidc_endpoint": oidc_config.get(session, "oidc_endpoint", ""),
            "oidc_client_secret": oidc_config.get(session, "oidc_client_secret", ""),
            "oidc_client_id": oidc_config.get(session, "oidc_client_id", ""),
            "oidc_scope": oidc_config.get(session, "oidc_scope", ""),
            "oidc_username_claim": oidc_config.get(session, "oidc_username_claim", ""),
            "oidc_group_claim": oidc_config.get(session, "oidc_group_claim", ""),
            "oidc_redirect_https": oidc_config.get_redirect_https(session),
            "oidc_logout_url": oidc_config.get(session, "oidc_logout_url", ""),
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
async def update_security(
    login_type: Annotated[LoginTypeEnum, Form()],
    request: Request,
    admin_user: Annotated[
        DetailedUser, Depends(get_authenticated_user(GroupEnum.admin))
    ],
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    access_token_expiry: Optional[int] = Form(None),
    min_password_length: Optional[int] = Form(None),
    oidc_endpoint: Optional[str] = Form(None),
    oidc_client_id: Optional[str] = Form(None),
    oidc_client_secret: Optional[str] = Form(None),
    oidc_scope: Optional[str] = Form(None),
    oidc_username_claim: Optional[str] = Form(None),
    oidc_group_claim: Optional[str] = Form(None),
    oidc_redirect_https: Optional[bool] = Form(False),
    oidc_logout_url: Optional[str] = Form(None),
):
    if (
        login_type in [LoginTypeEnum.basic, LoginTypeEnum.forms]
        and min_password_length is not None
    ):
        if min_password_length < 1:
            raise ToastException(
                "Minimum password length can't be 0 or negative", "error"
            )
        else:
            auth_config.set_min_password_length(session, min_password_length)

    if access_token_expiry is not None:
        if access_token_expiry < 1:
            raise ToastException("Access token expiry can't be 0 or negative", "error")
        else:
            auth_config.set_access_token_expiry_minutes(
                session, Minute(access_token_expiry)
            )

    if login_type == LoginTypeEnum.oidc:
        if oidc_endpoint:
            await oidc_config.set_endpoint(session, client_session, oidc_endpoint)
        if oidc_client_id:
            oidc_config.set(session, "oidc_client_id", oidc_client_id)
        if oidc_client_secret:
            oidc_config.set(session, "oidc_client_secret", oidc_client_secret)
        if oidc_scope:
            oidc_config.set(session, "oidc_scope", oidc_scope)
        if oidc_username_claim:
            oidc_config.set(session, "oidc_username_claim", oidc_username_claim)
        if oidc_redirect_https is not None:
            oidc_config.set(
                session,
                "oidc_redirect_https",
                "true" if oidc_redirect_https else "",
            )
        if oidc_logout_url:
            oidc_config.set(session, "oidc_logout_url", oidc_logout_url)
        if oidc_group_claim is not None:
            oidc_config.set(session, "oidc_group_claim", oidc_group_claim)

        error_message = await oidc_config.validate(session, client_session)
        if error_message:
            raise ToastException(error_message, "error")

    old = auth_config.get_login_type(session)
    auth_config.set_login_type(session, login_type)
    return template_response(
        "settings_page/security.html",
        request,
        admin_user,
        {
            "page": "security",
            "login_type": auth_config.get_login_type(session),
            "access_token_expiry": auth_config.get_access_token_expiry_minutes(session),
            "oidc_client_id": oidc_config.get(session, "oidc_client_id", ""),
            "oidc_scope": oidc_config.get(session, "oidc_scope", ""),
            "oidc_username_claim": oidc_config.get(session, "oidc_username_claim", ""),
            "oidc_group_claim": oidc_config.get(session, "oidc_group_claim", ""),
            "oidc_client_secret": oidc_config.get(session, "oidc_client_secret", ""),
            "oidc_endpoint": oidc_config.get(session, "oidc_endpoint", ""),
            "oidc_redirect_https": oidc_config.get_redirect_https(session),
            "oidc_logout_url": oidc_config.get(session, "oidc_logout_url", ""),
            "success": "Settings updated",
        },
        block_name="form",
        headers={} if old == login_type else {"HX-Refresh": "true"},
    )


@router.get("/indexers")
async def read_indexers(
    request: Request,
    admin_user: Annotated[
        DetailedUser, Depends(get_authenticated_user(GroupEnum.admin))
    ],
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
):
    contexts = await get_indexer_contexts(
        SessionContainer(session=session, client_session=client_session),
        check_required=False,
        return_disabled=True,
    )

    return template_response(
        "settings_page/indexers.html",
        request,
        admin_user,
        {
            "page": "indexers",
            "indexers": contexts,
        },
    )


@router.post("/indexers")
async def update_indexers(
    request: Request,
    admin_user: Annotated[
        DetailedUser, Depends(get_authenticated_user(GroupEnum.admin))
    ],
    indexer_select: Annotated[str, Form()],
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
):
    contexts = await get_indexer_contexts(
        SessionContainer(session=session, client_session=client_session),
        check_required=False,
        return_disabled=True,
    )

    updated_context: Optional[IndexerContext] = None
    for context in contexts:
        if context.indexer.name == indexer_select:
            updated_context = context
            break

    if not updated_context:
        raise ToastException("Indexer not found", "error")

    form_values = await request.form()

    for key, context in updated_context.configuration.items():
        value = form_values.get(key)
        if value is None:  # forms do not include false checkboxes
            if context.type is bool:
                value = False
            else:
                logger.error("Value is missing for key", key=key)
                continue
        if context.type is bool:
            indexer_configuration_cache.set_bool(session, key, value == "on")
        else:
            indexer_configuration_cache.set(session, key, str(value))

    flush_prowlarr_cache()

    raise ToastException("Indexers updated", "success")
