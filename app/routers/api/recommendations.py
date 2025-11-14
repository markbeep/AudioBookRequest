from typing import Annotated

from fastapi import APIRouter, Depends, Security
from sqlmodel import Session

from aiohttp import ClientSession
from app.internal.auth.authentication import ABRAuth, DetailedUser
from app.internal.audiobookshelf.client import abs_list_library_items
from app.internal.audiobookshelf.config import abs_config
from app.internal.book_search import get_region_from_settings, list_audible_books
from app.internal.models import BookRequest
from app.util.connection import get_connection
from app.util.db import get_session
from app.util.log import logger
from app.util.recommendations import (
    get_user_sims_recommendations_pooled_with_reasons,
)

router = APIRouter(prefix="/recommendations", tags=["Recommendations"])


@router.get("/for-you")
async def api_for_you_recommendations(
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    page: int = 1,
    per_page: int = 24,
    user: DetailedUser = Security(ABRAuth()),
):
    """JSON API for personalized recommendations with pagination.
    Returns a stable slice from a pooled recommendation list, plus 'why' reasons.
    """
    # Clamp pagination
    page = max(1, page)
    per_page = max(6, min(60, per_page))

    # ABS seeding similar to the page route
    abs_seeds: list[str] = []
    try:
        if abs_config.is_valid(session) and abs_config.get_library_id(session):
            abs_library: list[BookRequest] | None = await abs_list_library_items(
                session, client_session, limit=24
            )
            abs_seeds.extend([b.asin for b in (abs_library or []) if b.asin])

            # Resolve some missing ASINs via Audible search
            missing = [b for b in (abs_library or []) if not b.asin][:10]
            if missing:
                region = get_region_from_settings()
                for b in missing:
                    q = f"{b.title} {b.authors[0] if b.authors else ''}".strip()
                    if not q:
                        continue
                    try:
                        res = await list_audible_books(
                            session=session,
                            client_session=client_session,
                            query=q,
                            num_results=1,
                            page=0,
                            audible_region=region,
                        )
                        if res and res[0].asin and res[0].asin not in abs_seeds:
                            abs_seeds.append(res[0].asin)
                    except Exception as ie:
                        logger.debug(
                            "ABS seed resolve failed", title=b.title, error=str(ie)
                        )
    except Exception as e:
        logger.debug("ABS seeding skipped (API)", error=str(e))

    # Fetch a large pooled list and slice
    try:
        full_list, reasons = await get_user_sims_recommendations_pooled_with_reasons(
            session, client_session, user, seed_asins=abs_seeds, pool_size=240
        )
    except Exception as e:
        logger.warning("API For You recs failed, returning empty list", error=str(e))
        full_list = []
        reasons = {}

    start = (page - 1) * per_page
    end = start + per_page
    page_items = full_list[start:end]
    total_items = len(full_list)
    has_next = end < total_items

    # FastAPI can serialize SQLModel/Pydantic models directly
    return {
        "items": page_items,
        "reasons": {k: reasons.get(k) for k in [b.asin for b in page_items]},
        "page": page,
        "per_page": per_page,
        "has_next": has_next,
        "total_items": total_items,
    }
