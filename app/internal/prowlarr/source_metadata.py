import asyncio

from app.internal.indexers.abstract import SessionContainer
from app.internal.indexers.indexer_util import get_indexer_contexts
from app.internal.models import AudiobookRequest, ProwlarrSource
from app.util.log import logger


async def edit_source_metadata(
    book_request: AudiobookRequest,
    sources: list[ProwlarrSource],
    container: SessionContainer,
):
    contexts = await get_indexer_contexts(container)

    coros = [
        context.indexer.setup(book_request, container, context.valued)
        for context in contexts
    ]
    exceptions = await asyncio.gather(*coros, return_exceptions=True)
    for exc in exceptions:
        if exc:
            logger.error("Failed to setup indexer", error=str(exc))

    coros = []
    for source in sources:
        for context in contexts:
            if await context.indexer.is_matching_source(source, container):
                coros.append(context.indexer.edit_source_metadata(source, container))
                break

    exceptions = await asyncio.gather(*coros, return_exceptions=True)
    for exc in exceptions:
        if exc:
            logger.error("Failed to edit source metadata", error=str(exc))
