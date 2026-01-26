from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Security
from sqlmodel import Session, col, func, select

from app.internal.auth.authentication import ABRAuth, DetailedUser
from app.internal.models import (
    Audiobook,
    AudiobookRequest,
    GroupEnum,
    ManualBookRequest,
)
from app.util.db import get_session
from app.util.templates import template_response

router = APIRouter(prefix="/stats")


@router.get("")
async def read_stats(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    total_books = session.exec(select(func.count(Audiobook.asin))).one()
    downloaded_books = session.exec(
        select(func.count(Audiobook.asin)).where(Audiobook.downloaded.is_(True))
    ).one()
    total_requests = session.exec(
        select(func.count()).select_from(AudiobookRequest)
    ).one()
    unique_requests = session.exec(
        select(func.count(func.distinct(AudiobookRequest.asin)))
    ).one()

    pending_requests = session.exec(
        select(func.count(func.distinct(AudiobookRequest.asin)))
        .join(Audiobook)
        .where(
            Audiobook.downloaded.is_(False),
            AudiobookRequest.processing_status == "pending",
        )
    ).one()

    active_downloads = session.exec(
        select(func.count(func.distinct(AudiobookRequest.asin)))
        .join(Audiobook)
        .where(
            Audiobook.downloaded.is_(False),
            col(AudiobookRequest.processing_status).in_(
                AudiobookRequest.ACTIVE_DOWNLOAD_STATUSES
            ),
        )
    ).one()

    failed_requests = session.exec(
        select(func.count())
        .select_from(AudiobookRequest)
        .where(col(AudiobookRequest.processing_status).startswith("failed"))
    ).one()

    review_required = session.exec(
        select(func.count())
        .select_from(AudiobookRequest)
        .where(AudiobookRequest.processing_status == "review_required")
    ).one()

    manual_requests = session.exec(
        select(func.count())
        .select_from(ManualBookRequest)
        .where(ManualBookRequest.downloaded.is_(False))
    ).one()

    now = datetime.now()
    last_24h = now - timedelta(days=1)
    last_7d = now - timedelta(days=7)
    last_30d = now - timedelta(days=30)

    requests_24h = session.exec(
        select(func.count())
        .select_from(AudiobookRequest)
        .where(AudiobookRequest.updated_at >= last_24h)
    ).one()
    requests_7d = session.exec(
        select(func.count())
        .select_from(AudiobookRequest)
        .where(AudiobookRequest.updated_at >= last_7d)
    ).one()
    requests_30d = session.exec(
        select(func.count())
        .select_from(AudiobookRequest)
        .where(AudiobookRequest.updated_at >= last_30d)
    ).one()

    top_requested_rows = session.exec(
        select(
            Audiobook.title,
            func.count(AudiobookRequest.asin).label("request_count"),
        )
        .join(AudiobookRequest)
        .group_by(Audiobook.asin)
        .order_by(func.count(AudiobookRequest.asin).desc())
        .limit(6)
    ).all()
    top_requested = [
        {"title": row[0], "count": row[1]} for row in top_requested_rows
    ]

    recent_requests_rows = session.exec(
        select(Audiobook.title, AudiobookRequest.updated_at)
        .join(AudiobookRequest)
        .order_by(AudiobookRequest.updated_at.desc())
        .limit(6)
    ).all()
    recent_requests = [
        {
            "title": row[0],
            "updated_at": row[1].strftime("%b %d %H:%M"),
        }
        for row in recent_requests_rows
    ]

    return template_response(
        "settings_page/stats.html",
        request,
        admin_user,
        {
            "page": "stats",
            "total_books": total_books,
            "downloaded_books": downloaded_books,
            "total_requests": total_requests,
            "unique_requests": unique_requests,
            "pending_requests": pending_requests,
            "active_downloads": active_downloads,
            "failed_requests": failed_requests,
            "review_required": review_required,
            "manual_requests": manual_requests,
            "requests_24h": requests_24h,
            "requests_7d": requests_7d,
            "requests_30d": requests_30d,
            "top_requested": top_requested,
            "recent_requests": recent_requests,
        },
    )
