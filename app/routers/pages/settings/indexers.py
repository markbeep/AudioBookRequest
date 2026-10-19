import json
from collections.abc import Mapping
from contextlib import asynccontextmanager
from typing import Annotated, Literal, cast

from aiohttp import ClientSession
from anyio import Path
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import APIRouter, Depends, FastAPI, Form, Request, Security
from sqlmodel import Session

from app.internal.auth.authentication import ABRAuth, DetailedUser
from app.internal.indexers.abstract import SessionContainer
from app.internal.indexers.configuration import indexer_configuration_cache
from app.internal.indexers.indexer_util import (
    get_indexer_contexts,
    update_single_indexer,
)
from app.internal.models import GroupEnum
from app.util.cache import StringConfigCache
from app.util.connection import get_connection
from app.util.db import get_session
from app.util.log import logger
from app.util.templates import catalog_response
from app.util.toast import ToastException

IndexerConfigKey = Literal["indexers_configuration_file"]
indexer_config = StringConfigCache[IndexerConfigKey]()
last_modified = 0


async def check_indexer_file_changes():
    with next(get_session()) as session:
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


async def read_indexer_file(
    session: Session, client_session: ClientSession, *, file_path: str | None = None
):
    if not file_path:
        file_path = indexer_config.get(session, "indexers_configuration_file")
    if not file_path:
        return
    try:
        config_path = Path(file_path)
        values = cast(object, json.loads(await config_path.read_text()))
        global last_modified
        if (lm := (await config_path.stat()).st_mtime) == last_modified:
            return
        last_modified = lm
    except Exception as e:
        raise ValueError(f"Failed to read file: {e}")

    if not isinstance(values, dict):
        raise TypeError("File does not contain a valid JSON object")

    for key in values:  # pyright: ignore[reportUnknownVariableType]
        if isinstance(key, str):
            raise TypeError("File contains non-string keys")
    values = cast(Mapping[str, object], values)

    for indexer, indexer_values in values.items():
        if not isinstance(indexer_values, dict):
            raise TypeError(f"Indexer values for {indexer} is not a valid object/dict")
        for key in indexer_values:  # pyright: ignore[reportUnknownVariableType]
            if not isinstance(key, str):
                raise TypeError(
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

    return catalog_response(
        "Settings.Indexers",
        user=admin_user,
        indexers=contexts,
        file_path=file_path,
    )


@router.post("/hx-read-file")
async def read_file_configuration(
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
    file_path: Annotated[str | None, Form()] = None,
):
    _ = admin_user
    if file_path is None or file_path.strip() == "":
        indexer_configuration_cache.set(session, "indexers_configuration_file", "")
        raise ToastException("Configuration file cleared", "success")
    try:
        await read_indexer_file(session, client_session, file_path=file_path)
    except Exception as e:
        logger.error("Failed to read indexer configuration file", error=str(e))
        raise ToastException(str(e), "error")

    indexer_configuration_cache.set(session, "indexers_configuration_file", file_path)

    raise ToastException("Configuration file updated", "success", cause_refresh=True)


@router.post("/hx-save")
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
