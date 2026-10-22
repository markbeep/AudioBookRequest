from collections.abc import Sequence
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Query, Security

from app.internal.auth.authentication import ABRAuth, DetailedUser
from app.internal.env_settings import Settings
from app.internal.models import GroupEnum
from app.util.log import LogEntry, snapshot_logs
from app.util.templates import catalog_response

router = APIRouter(prefix="/logs")

LOG_LEVELS = ("debug", "info", "warning", "error")
PAGE_SIZE = 250


def _logs_url(levels: Sequence[str], offset: int = 0) -> str:
    params: dict[str, str] = {}
    if set(levels) != set(LOG_LEVELS):
        params["level"] = ",".join(levels)
    if offset > 0:
        params["offset"] = str(offset)
    base = Settings().app.base_url.rstrip("/")
    return f"{base}/settings/logs" + (f"?{urlencode(params)}" if params else "")


@router.get("")
def read_logs(
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
    level: Annotated[str | None, Query()] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    if level is None:
        selected_levels = list(LOG_LEVELS)
    else:
        requested = {lvl.strip().lower() for lvl in level.split(",")}
        selected_levels = [lvl for lvl in LOG_LEVELS if lvl in requested]

    matching: list[LogEntry] = [
        entry for entry in snapshot_logs() if entry["level"] in selected_levels
    ]
    offset = min(offset, len(matching))
    end = len(matching) - offset
    start = max(0, end - PAGE_SIZE)
    logs = matching[start:end]

    toggle_urls: dict[str, str] = {}
    for lvl in LOG_LEVELS:
        if lvl in selected_levels:
            toggled = [other for other in selected_levels if other != lvl]
        else:
            toggled = [
                other
                for other in LOG_LEVELS
                if other in selected_levels or other == lvl
            ]
        toggle_urls[lvl] = _logs_url(toggled)

    return catalog_response(
        "Settings.Logs.Index",
        user=admin_user,
        logs=logs,
        log_levels=list(LOG_LEVELS),
        selected_levels=selected_levels,
        toggle_urls=toggle_urls,
        older_url=_logs_url(selected_levels, offset + PAGE_SIZE) if start > 0 else None,
        newer_url=_logs_url(selected_levels, max(0, offset - PAGE_SIZE))
        if offset > 0
        else None,
    )
