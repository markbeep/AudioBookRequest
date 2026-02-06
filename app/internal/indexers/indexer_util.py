# pyright: reportExplicitAny=false

from typing import Any, Mapping

from aiohttp import ClientSession
from pydantic import BaseModel
from sqlmodel import Session

from app.internal.indexers.abstract import AbstractIndexer, SessionContainer
from app.internal.indexers.configuration import (
    ConfigurationException,
    Configurations,
    IndexerConfiguration,
    ValuedConfigurations,
    create_valued_configuration,
    indexer_configuration_cache,
)
from app.internal.indexers.indexers import indexers
from app.internal.prowlarr.util import flush_prowlarr_cache
from app.util.json_type import get_bool
from app.util.log import logger


class IndexerContext(BaseModel, arbitrary_types_allowed=True):
    indexer: AbstractIndexer[Configurations]
    configuration: dict[str, IndexerConfiguration[Any]]
    valued: ValuedConfigurations
    enabled: bool


async def get_indexer_contexts(
    container: SessionContainer,
    *,
    check_required: bool = True,
    return_disabled: bool = False,
) -> list[IndexerContext]:
    """Builds the configuration contexts with default values and types of each value filled in for all indexers."""

    logger.debug(
        "Getting indexer contexts",
        check_required=check_required,
        return_disabled=return_disabled,
    )
    contexts: list[IndexerContext] = []
    for Indexer in indexers:
        try:
            configuration = await Indexer.get_configurations(container)
            filtered_configuration: dict[str, IndexerConfiguration[Any]] = dict()
            for k, v in vars(configuration).items():  # pyright: ignore[reportAny]
                if isinstance(v, IndexerConfiguration):
                    filtered_configuration[k] = v

            valued_configuration = create_valued_configuration(
                configuration,
                container.session,
                check_required=check_required,
            )

            indexer = Indexer()

            indexer_enabled = await indexer.is_enabled(container, valued_configuration)

            if not return_disabled and not indexer_enabled:
                logger.debug("Indexer is disabled", name=Indexer.name)
                continue

            contexts.append(
                IndexerContext(
                    indexer=indexer,
                    configuration=filtered_configuration,
                    valued=valued_configuration,
                    enabled=indexer_enabled,
                )
            )
        except ConfigurationException as e:
            logger.error(
                "Failed to get configurations for Indexer",
                name=Indexer.name,
                error=str(e),
            )

    return contexts


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
