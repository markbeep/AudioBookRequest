# pyright: reportExplicitAny=false

from typing import Any

from pydantic import BaseModel

from app.internal.indexers.abstract import AbstractIndexer, SessionContainer
from app.internal.indexers.configuration import (
    ConfigurationException,
    Configurations,
    IndexerConfiguration,
    ValuedConfigurations,
    create_valued_configuration,
)
from app.internal.indexers.indexers import indexers
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
