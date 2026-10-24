"""Structured logging configuration and request context tracking."""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar

# ContextVar to propagate request_id across async call chains
request_id_ctx: ContextVar[str | None] = ContextVar("request_id_ctx", default=None)


class RequestIdFilter(logging.Filter):
    """Inject current request_id into log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get() or "system"  # type: ignore[attr-defined]
        return True


def setup_logging(log_level: str = "INFO") -> None:
    """Configure root logger with structured formatting and request ID injection."""
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level.upper())

    # Avoid duplicating handlers if already initialized
    if not root_logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.addFilter(RequestIdFilter())
        formatter = logging.Formatter(
            fmt="[%(asctime)s] [%(levelname)s] [req:%(request_id)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%SZ",
        )
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)


logger = logging.getLogger("voice_platform")
