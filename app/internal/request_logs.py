from __future__ import annotations

from typing import Iterable

from sqlmodel import Session, select

from app.internal.models import RequestLog, RequestLogLevel


def log_request_event(
    session: Session,
    asin: str,
    user_username: str | None,
    message: str,
    level: RequestLogLevel = RequestLogLevel.info,
    commit: bool = True,
) -> RequestLog:
    log_entry = RequestLog(
        asin=asin,
        user_username=user_username,
        message=message,
        level=level,
    )
    session.add(log_entry)
    if commit:
        session.commit()
    return log_entry


def get_request_logs(
    session: Session,
    asin: str,
    user_username: str | None = None,
    limit: int = 6,
) -> Iterable[RequestLog]:
    statement = select(RequestLog).where(RequestLog.asin == asin)
    if user_username:
        statement = statement.where(RequestLog.user_username == user_username)
    return session.exec(
        statement.order_by(RequestLog.created_at.desc()).limit(limit)
    ).all()
