from typing import Annotated

from aiohttp import ClientSession
from fastapi import APIRouter, Depends, Form, Request, Response, Security
from sqlmodel import Session

from app.internal.auth.authentication import ABRAuth, DetailedUser
from app.internal.models import GroupEnum
from app.internal.ai.config import ai_config
from app.util.connection import get_connection
from app.util.db import get_session
from app.util.templates import template_response


router = APIRouter(prefix="/ai")


@router.get("")
async def read_ai_settings(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    admin_user: DetailedUser = Security(ABRAuth(GroupEnum.admin)),
):
    endpoint = ai_config.get_endpoint(session) or ""
    model = ai_config.get_model(session) or ""
    return template_response(
        "settings_page/ai.html",
        request,
        admin_user,
        {
            "page": "ai",
            "ai_endpoint": endpoint,
            "ai_model": model,
        },
    )


@router.put("/endpoint")
def update_ai_endpoint(
    endpoint: Annotated[str, Form(alias="endpoint")],
    session: Annotated[Session, Depends(get_session)],
    admin_user: DetailedUser = Security(ABRAuth(GroupEnum.admin)),
):
    ai_config.set_endpoint(session, endpoint)
    return Response(status_code=204, headers={"HX-Refresh": "true"})


@router.put("/model")
def update_ai_model(
    model: Annotated[str, Form(alias="model")],
    session: Annotated[Session, Depends(get_session)],
    admin_user: DetailedUser = Security(ABRAuth(GroupEnum.admin)),
):
    ai_config.set_model(session, model)
    return Response(status_code=204, headers={"HX-Refresh": "true"})


@router.post("/test")
async def test_ai_connection(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    admin_user: DetailedUser = Security(ABRAuth(GroupEnum.admin)),
):
    """Attempt to contact the Ollama endpoint and verify model presence. Returns a tiny HTML snippet suitable for HTMX target."""
    from fastapi import Response as FastAPIResponse

    endpoint = ai_config.get_endpoint(session)
    model = ai_config.get_model(session)
    status: str
    detail: str = ""
    ok = False
    if not endpoint or not model:
        status = "not_configured"
        detail = "Endpoint or model not set."
    else:
        # Try to list tags (models)
        try:
            async with client_session.get(f"{endpoint}/api/tags", timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    tags = [t.get("name") for t in data.get("models", [])] if isinstance(data, dict) else []
                    if model in (tags or []):
                        ok = True
                        status = "ok"
                        detail = f"Model '{model}' is available."
                    else:
                        ok = False
                        status = "model_missing"
                        detail = f"Model '{model}' not found among available models."
                else:
                    ok = False
                    status = "unreachable"
                    detail = f"Tags endpoint returned status {resp.status}."
        except Exception as e:
            ok = False
            status = "unreachable"
            detail = f"Failed to reach endpoint: {e}"

        # Optional: quick generate sanity check
        if ok:
            try:
                body = {"model": model, "prompt": "Return JSON: {\"ping\":\"pong\"}", "format": "json", "stream": False}
                async with client_session.post(f"{endpoint}/api/generate", json=body, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        if isinstance(data, dict) and data.get("response"):
                            ok = True
                        else:
                            ok = False
                            status = "generate_failed"
                            detail = "Generate returned unexpected payload."
                    else:
                        ok = False
                        status = "generate_failed"
                        detail = f"Generate returned status {resp.status}."
            except Exception as e:
                ok = False
                status = "generate_failed"
                detail = f"Generate failed: {e}"

    # Decide alert style based on status
    if ok:
        cls = "alert-success"
    elif status in {"model_missing", "unreachable", "generate_failed", "not_configured"}:
        cls = "alert-error"
    else:
        cls = "alert-warning"

    html = f"<div class='alert {cls}'><span>{detail or status}</span></div>"
    return FastAPIResponse(content=html, media_type="text/html")
