from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Response
from sqlmodel import Session

from app.internal.auth.authentication import create_user, raise_for_invalid_password
from app.internal.auth.config import auth_config
from app.internal.auth.login_types import LoginTypeEnum
from app.internal.env_settings import Settings
from app.internal.models import GroupEnum
from app.util.censor import censor
from app.util.db import get_session
from app.util.log import logger
from app.util.redirect import BaseUrlRedirectResponse
from app.util.templates import catalog_response
from app.util.toast import ToastException

router = APIRouter(prefix="/init")


@router.get("")
def read_init(session: Annotated[Session, Depends(get_session)]):
    init_username = Settings().app.init_root_username.strip()
    init_password = Settings().app.init_root_password.strip()

    try:
        login_type = Settings().app.get_force_login_type()
        if login_type == LoginTypeEnum.oidc and (
            not init_username.strip() or not init_password.strip()
        ):
            raise ValueError(
                "OIDC login type is not supported for initial setup without an initial username/password."
            )
    except ValueError as e:
        logger.error(f"Invalid force login type: {e}")
        login_type = None

    if init_username and init_password:
        logger.info(
            "Initial root credentials provided. Skipping init page.",
            username=censor(init_username),
            login_type=login_type,
        )
        if login_type is None:
            logger.warning(
                "No login type set. Defaulting to 'forms'.",
                username=censor(init_username),
            )
            login_type = LoginTypeEnum.forms

        user = create_user(init_username, init_password, GroupEnum.admin, root=True)
        session.add(user)
        auth_config.set_login_type(session, login_type)
        session.commit()
        if login_type == LoginTypeEnum.oidc:
            return BaseUrlRedirectResponse("/login?backup=1")
        else:
            return BaseUrlRedirectResponse("/login")

    elif init_username or init_password:
        logger.warning(
            "Initial root credentials provided but missing either username or password. Skipping initialization through environment variables.",
            set_username=bool(init_username),
            set_password=bool(init_password),
        )

    return catalog_response("Init", force_login_type=login_type)


@router.post("/hx-init")
def create_init(
    login_type: Annotated[LoginTypeEnum, Form()],
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    confirm_password: Annotated[str, Form()],
    session: Annotated[Session, Depends(get_session)],
):
    if username.strip() == "":
        raise ToastException("Username cannot be empty", type="error")

    try:
        raise_for_invalid_password(session, password, confirm_password)
    except HTTPException as e:
        raise ToastException(e.detail, type="error") from e

    user = create_user(username, password, GroupEnum.admin, root=True)
    session.add(user)
    auth_config.set_login_type(session, login_type)
    session.commit()

    return Response(status_code=201, headers={"HX-Redirect": "/"})
