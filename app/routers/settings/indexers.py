import json
import os
from contextlib import asynccontextmanager
from typing import Annotated, Literal, Mapping, cast

from aiohttp import ClientSession
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import APIRouter, Depends, FastAPI, Form, Request, Security
from sqlmodel import Session

from app.internal.auth.authentication import ABRAuth, DetailedUser
from app.internal.indexers.abstract import SessionContainer
from app.internal.indexers.configuration import indexer_configuration_cache
from app.internal.indexers.indexer_util import IndexerContext, get_indexer_contexts
from app.internal.models import GroupEnum
from app.internal.prowlarr.prowlarr import flush_prowlarr_cache
from app.util.cache import StringConfigCache
from app.util.connection import get_connection
from app.util.db import get_session, open_session
from app.util.json_type import get_bool
from app.util.log import logger
from app.util.templates import template_response
from app.util.toast import ToastException

IndexerConfigKey = Literal["indexers_configuration_file"]
indexer_config = StringConfigCache[IndexerConfigKey]()
last_modified = 0


async def check_indexer_file_changes():
    with open_session() as session:
        async with ClientSession() as client_session:
            try:
                await read_indexer_file(session, client_session)
            except Exception as e:
                logger.error("Failed to read indexer configuration file", error=str(e))


@asynccontextmanager
async def lifespan(app: FastAPI):
    _ = app
    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_indexer_file_changes, "interval", seconds=15)
    scheduler.start()
    yield
    scheduler.shutdown()


router = APIRouter(prefix="/indexers", lifespan=lifespan)


async def update_single_indexer(
    indexer_select: str,
    values: Mapping[str, object],
    session: Session,
    client_session: ClientSession,
    ignore_missing_booleans: bool = False,
):
    """
    Update a single indexer with the given values.

    `ignore_missing_booleans` can be set to true to ignore missing boolean values. By default, missing booleans are treated as false.
    """

    session_container = SessionContainer(session=session, client_session=client_session)
    contexts = await get_indexer_contexts(
        session_container, check_required=False, return_disabled=True
    )

    updated_context: IndexerContext | None = None
    for context in contexts:
        if context.indexer.name == indexer_select:
            updated_context = context
            break

    if not updated_context:
        raise ValueError("Indexer not found")

    for key, context in updated_context.configuration.items():
        value = values.get(key)
        if value is None:
            # forms do not include false checkboxes, so we handle missing booleans as false
            if context.type_ is bool and not ignore_missing_booleans:
                value = False
            else:
                logger.warning("Value is missing for key", key=key)
                continue
        if context.type_ is bool:
            indexer_configuration_cache.set_bool(session, key, value == "on")
        else:
            indexer_configuration_cache.set(session, key, str(value))

    if "enabled" in values and (
        isinstance(e := values["enabled"], str)
        or isinstance(e, bool)
        or isinstance(e, int)
    ):
        logger.debug("Setting enabled state", enabled=values["enabled"])
        enabled = get_bool(e) or False
        await updated_context.indexer.set_enabled(
            session_container,
            enabled,
        )

    flush_prowlarr_cache()


async def read_indexer_file(
    session: Session, client_session: ClientSession, *, file_path: str | None = None
):
    if not file_path:
        file_path = indexer_config.get(session, "indexers_configuration_file")
    if not file_path:
        return
    try:
        with open(file_path, "r") as f:
            values = cast(object, json.load(f))
            global last_modified
            if (lm := os.path.getmtime(file_path)) == last_modified:
                return
            else:
                last_modified = lm
    except Exception as e:
        raise ValueError(f"Failed to read file: {e}")

    if not isinstance(values, dict):
        raise ValueError("File does not contain a valid JSON object")

    for key in values.keys():  # pyright: ignore[reportUnknownVariableType]
        if isinstance(key, str):
            raise ValueError("File contains non-string keys")
    values = cast(Mapping[str, object], values)

    for indexer, indexer_values in values.items():
        if not isinstance(indexer_values, dict):
            raise ValueError(f"Indexer values for {indexer} is not a valid object/dict")
        for key in indexer_values.keys():  # pyright: ignore[reportUnknownVariableType]
            if not isinstance(key, str):
                raise ValueError(
                    f"Indexer values for {indexer} contains non-string keys"
                )
        indexer_values = cast(Mapping[str, object], indexer_values)

        await update_single_indexer(
            indexer,
            indexer_values,
            session,
            client_session,
            ignore_missing_booleans=True,
        )

    logger.info(
        "Successfully read updated indexer configuration file",
        file_path=file_path,
    )


@router.get("")
async def read_indexers(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    file_path = indexer_config.get(session, "indexers_configuration_file")
    if file_path:
        try:
            await read_indexer_file(session, client_session, file_path=file_path)
        except Exception as e:
            logger.warning(
                "Failed to read indexer configuration file. Ignoring.", error=str(e)
            )

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
            "file_path": file_path or "",
        },
    )


@router.post("/read-file")
async def read_file_configuration(
    file_path: Annotated[str, Form()],
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    _ = admin_user
    if file_path.strip() == "":
        indexer_configuration_cache.set(session, "indexers_configuration_file", "")
        raise ToastException("Configuration file cleared", "success")
    try:
        await read_indexer_file(session, client_session, file_path=file_path)
    except Exception as e:
        logger.error("Failed to read indexer configuration file", error=str(e))
        raise ToastException(str(e), "error")

    indexer_configuration_cache.set(session, "indexers_configuration_file", file_path)

    raise ToastException("Configuration file updated", "success", cause_refresh=True)


@router.post("")
async def update_indexers(
    request: Request,
    indexer_select: Annotated[str, Form()],
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    _ = admin_user
    values = dict(await request.form())
    values["enabled"] = values.get("enabled", "off")  # handle missing checkbox
    try:
        await update_single_indexer(
            indexer_select,
            values,
            session,
            client_session,
        )
    except ValueError as e:
        raise ToastException(str(e), "error")

    raise ToastException("Indexers updated", "success")
