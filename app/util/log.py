import logging
import threading
from collections import deque
from typing import TypedDict

import structlog
from structlog.typing import EventDict


class LogEntry(TypedDict):
    level: str
    message: str


# in-memory only, reset on restart. shortcut: capped so a long-running instance cannot grow unbounded, raise if full history is needed
logs: deque[LogEntry] = deque(maxlen=10_000)
_logs_lock = threading.Lock()

_plain_renderer = structlog.dev.ConsoleRenderer(colors=False)


def snapshot_logs() -> list[LogEntry]:
    with _logs_lock:
        return list(logs)


def _capture_log_event(
    logger: logging.Logger, method_name: str, event_dict: EventDict
) -> EventDict:
    message = _plain_renderer(logger, method_name, dict(event_dict))
    with _logs_lock:
        logs.append({"level": method_name, "message": message})
    return event_dict


structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False),
        _capture_log_event,
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.NOTSET),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=False,
)

logger = structlog.stdlib.get_logger()
