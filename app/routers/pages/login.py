from urllib.parse import urlencode

from fastapi import APIRouter, Request

from app.util.redirect import BaseUrlRedirectResponse

router = APIRouter(prefix="/login")


@router.get("")
def redirect_login(request: Request):
    if qp := urlencode(request.query_params):
        return BaseUrlRedirectResponse("/auth/login?" + qp)
    return BaseUrlRedirectResponse("/auth/login")
