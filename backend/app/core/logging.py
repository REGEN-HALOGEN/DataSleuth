"""Fail-closed structured logging: never serialize arbitrary application data.

Log records deliberately discard messages, arguments, extras and tracebacks.
Only explicitly approved static event identifiers may be emitted.
"""

import json
import logging
import sys
from datetime import datetime, timezone

EVENTS = frozenset(
    {
        "service_started",
        "service_stopped",
        "dependency_unavailable",
        "startup_failed",
        "account_operation_failed",
        "scan_worker_started",
        "scan_worker_storage_unavailable",
        "scan_worker_stopped_unexpectedly",
    }
)


class SafeJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        event = (
            record.msg
            if isinstance(record.msg, str) and record.msg in EVENTS
            else "event_redacted"
        )
        return json.dumps(
            {
                "timestamp": datetime.fromtimestamp(
                    record.created, timezone.utc
                ).isoformat(),
                "level": logging.getLevelName(record.levelno)
                if record.levelno in (10, 20, 30, 40, 50)
                else "UNKNOWN",
                "event": event,
            },
            separators=(",", ":"),
        )


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(SafeJsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    # Uvicorn's default access formatter includes raw paths and query strings.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
