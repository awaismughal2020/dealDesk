"""Structured JSON logging with correlation IDs and redaction of sensitive fields."""

from __future__ import annotations

import logging
import sys
from collections.abc import MutableMapping
from typing import Any

import structlog

#: Keys whose values must never reach the logs (brief content, prose, credentials, personal data).
REDACTED_KEYS = frozenset(
    {
        "brief",
        "brief_text",
        "text",
        "content",
        "prompt",
        "completion",
        "password",
        "token",
        "access_token",
        "refresh_token",
        "authorization",
        "cookie",
        "email",
        "display_name",
        "comment",
    }
)
REDACTED = "[REDACTED]"


def redact_sensitive(
    _logger: object, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Replace sensitive values with a marker. Only metadata is logged."""
    for key in list(event_dict):
        if key.lower() in REDACTED_KEYS:
            event_dict[key] = REDACTED
    return event_dict


def configure_logging(level: str = "INFO") -> None:
    """Configure structlog for JSON output to stdout. Safe to call more than once."""
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level.upper(), force=True)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            redact_sensitive,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level.upper())),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )


def get_logger(name: str) -> structlog.typing.FilteringBoundLogger:
    """Return a structured logger bound to a component name."""
    logger: structlog.typing.FilteringBoundLogger = structlog.get_logger(name)
    return logger.bind(component=name)
