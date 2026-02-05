import json
from typing import Annotated, cast

from aiohttp import ClientSession
from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response, Security
from sqlmodel import Session

from app.internal.auth.authentication import AnyAuth, DetailedUser
from app.internal.indexers.abstract import SessionContainer
from app.internal.indexers.indexer_util import (
    get_indexer_contexts,
    update_single_indexer,
)
from app.internal.models import BaseSQLModel, GroupEnum
from app.util.connection import get_connection
from app.util.db import get_session
from app.util.log import logger
from app.util.toast import ToastException

router = APIRouter(prefix="/indexers", tags=["Indexers"])


@router.patch("/{indexer}")
async def update_indexer(
    indexer: Annotated[
        str, Path(description="The indexer name (case-sensitive) to update")
    ],
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    _: Annotated[DetailedUser, Security(AnyAuth(GroupEnum.admin))],
):
    """
    Update values of an indexer. The body needs to be a key-value mapping of the configuration values to update.

    Use the /configurations endpoint to get the list of configuration keys and their types.
    """

    try:
        body = await request.json()  # pyright: ignore[reportAny]
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="Body must be a JSON object")
        for key in body.keys():  # pyright: ignore[reportUnknownVariableType]
            if not isinstance(key, str):
                raise HTTPException(
                    status_code=400, detail="All keys in the body must be strings"
                )
        body = cast(dict[str, object], body)
        await update_single_indexer(
            indexer,
            body,
            session,
            client_session,
            ignore_missing_booleans=True,
        )
    except ToastException as e:
        logger.error(f"Error updating indexer {indexer}: {e.message}")
        raise HTTPException(status_code=400, detail=e.message)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    return Response(status_code=204)


class StringConfigurationResponse(BaseSQLModel):
    name: str
    description: str | None = None
    default: str | None = None
    required: bool
    type: str


@router.get(
    "/configurations", response_model=dict[str, list[StringConfigurationResponse]]
)
async def get_indexer_configurations(
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    _: Annotated[DetailedUser, Security(AnyAuth(GroupEnum.admin))],
):
    contexts = await get_indexer_contexts(
        SessionContainer(session=session, client_session=client_session),
        check_required=False,
        return_disabled=True,
    )

    stringified_contexts: dict[str, list[StringConfigurationResponse]] = {}
    for context in contexts:
        stringified_context = [
            StringConfigurationResponse(
                name=key,
                description=config.description,
                default=str(config.default) if config.default is not None else None,  # pyright: ignore[reportAny]
                required=config.required,
                type=config.type_.__name__,
            )
            for key, config in context.configuration.items()
        ]

        stringified_contexts[context.indexer.name] = stringified_context

    return stringified_contexts
