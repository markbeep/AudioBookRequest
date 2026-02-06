from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Request,
    Response,
    Security,
    status,
)
from sqlmodel import Session

from app.internal.auth.authentication import (
    ABRAuth,
    DetailedUser,
)
from app.internal.auth.config import auth_config
from app.internal.auth.login_types import LoginTypeEnum
from app.internal.auth.oidc_config import oidc_config
from app.util.db import get_session

router = APIRouter(prefix="/logout")


@router.post("")
async def logout(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    _: Annotated[DetailedUser, Security(ABRAuth())],
):
    request.session["sub"] = ""

    login_type = auth_config.get_login_type(session)
    if login_type == LoginTypeEnum.oidc:
        logout_url = oidc_config.get(session, "oidc_logout_url")
        if logout_url:
            return Response(
                status_code=status.HTTP_204_NO_CONTENT,
                headers={"HX-Redirect": logout_url},
            )
    return Response(
        status_code=status.HTTP_204_NO_CONTENT, headers={"HX-Redirect": "/login"}
    )
