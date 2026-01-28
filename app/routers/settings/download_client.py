from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Form, Request, Response, Security
from sqlmodel import Session

from app.internal.auth.authentication import ABRAuth, DetailedUser
from app.internal.models import GroupEnum
from app.internal.download_clients.config import download_client_config
from app.util.db import get_session
from app.util.templates import template_response
from app.util.toast import ToastException

router = APIRouter(prefix="/download-client")


@router.get("")
async def read_download_client(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    return template_response(
        "settings_page/download_client.html",
        request,
        admin_user,
        {
            "page": "download-client",
            "qbit_enabled": download_client_config.get_qbit_enabled(session),
            "qbit_host": download_client_config.get_qbit_host(session),
            "qbit_port": download_client_config.get_qbit_port(session),
            "qbit_user": download_client_config.get_qbit_user(session),
            "qbit_pass": download_client_config.get_qbit_pass(session),
            "qbit_category": download_client_config.get_qbit_category(session),
            "qbit_save_path": download_client_config.get_qbit_save_path(session),
            "qbit_complete_action": download_client_config.get_qbit_complete_action(
                session
            ),
        },
    )


@router.put("/enabled")
async def update_qbit_enabled(
    enabled: Annotated[bool, Form()] = False,
    session: Session = Depends(get_session),
    admin_user: DetailedUser = Security(ABRAuth(GroupEnum.admin)),
):
    _ = admin_user
    download_client_config.set_qbit_enabled(session, enabled)
    return Response(status_code=204)


@router.put("/connection")
async def update_qbit_connection(
    request: Request,
    host: Annotated[str, Form()],
    port: Annotated[int, Form()],
    username: Annotated[Optional[str], Form()] = None,
    password: Annotated[Optional[str], Form()] = None,
    session: Session = Depends(get_session),
    admin_user: DetailedUser = Security(ABRAuth(GroupEnum.admin)),
):
    download_client_config.set_qbit_host(session, host)
    download_client_config.set_qbit_port(session, port)
    if username is not None:
        download_client_config.set_qbit_user(session, username)
    if password is not None and password != "":
        download_client_config.set_qbit_pass(session, password)

    return template_response(
        "settings_page/download_client.html",
        request,
        admin_user,
        {
            "page": "download-client",
            "success_connection": "Connection settings updated",
            "qbit_enabled": download_client_config.get_qbit_enabled(session),
            "qbit_host": host,
            "qbit_port": port,
            "qbit_user": username,
            "qbit_pass": download_client_config.get_qbit_pass(session),
            "qbit_category": download_client_config.get_qbit_category(session),
            "qbit_save_path": download_client_config.get_qbit_save_path(session),
        },
        block_name="connection_form",
    )


@router.put("/settings")
async def update_qbit_settings(
    request: Request,
    category: Annotated[str, Form()],
    save_path: Annotated[Optional[str], Form()] = None,
    complete_action: Annotated[str, Form()] = "copy",
    session: Session = Depends(get_session),
    admin_user: DetailedUser = Security(ABRAuth(GroupEnum.admin)),
):
    download_client_config.set_qbit_category(session, category)
    if save_path is not None:
        download_client_config.set_qbit_save_path(session, save_path)
    download_client_config.set_qbit_complete_action(session, complete_action)

    return template_response(
        "settings_page/download_client.html",
        request,
        admin_user,
        {
            "page": "download-client",
            "success_settings": "Client settings updated",
            "qbit_enabled": download_client_config.get_qbit_enabled(session),
            "qbit_host": download_client_config.get_qbit_host(session),
            "qbit_port": download_client_config.get_qbit_port(session),
            "qbit_user": download_client_config.get_qbit_user(session),
            "qbit_pass": download_client_config.get_qbit_pass(session),
            "qbit_category": category,
            "qbit_save_path": save_path,
            "qbit_complete_action": download_client_config.get_qbit_complete_action(
                session
            ),
        },
        block_name="settings_form",
    )


@router.post("/test")
async def test_qbit_connection(
    request: Request,
    session: Session = Depends(get_session),
    host: Annotated[Optional[str], Form()] = None,
    port: Annotated[Optional[int], Form()] = None,
    username: Annotated[Optional[str], Form()] = None,
    password: Annotated[Optional[str], Form()] = None,
    admin_user: DetailedUser = Security(ABRAuth(GroupEnum.admin)),
):
    from app.internal.download_clients.qbittorrent import QbittorrentClient

    # Use password from DB if it wasn't provided (e.g. it was masked)
    if password == "" or password is None:
        password = download_client_config.get_qbit_pass(session)

    client = QbittorrentClient(
        session, host=host, port=port, username=username, password=password
    )
    success, status_code, error_msg = await client.test_connection()
    if success:
        return template_response(
            "base.html",
            request,
            None,
            {
                "toast_success": f"qBittorrent connection successful at {client.base_url}!"
            },
            headers={"HX-Retarget": "#toast-block", "HX-Reswap": "innerHTML"},
            block_name="toast_block",
        )
    else:
        hint = ""
        if status_code == 404:
            hint = " (Check if qBittorrent has a WebUI Root Folder configured)"
        elif status_code == 403:
            hint = " (Incorrect username or password)"
        elif status_code == 0:
            hint = " (Check if the host and port are correct and reachable from the container)"
            if host == "localhost" or host == "127.0.0.1":
                hint += ". WARNING: 'localhost' inside Docker refers to the container itself, not your PC. Use 'qbittorrent' or your host IP instead."

        raise ToastException(
            f"Failed to connect to qBittorrent at {client.base_url}. Status {status_code}: {error_msg}{hint}",
            "error",
        )
