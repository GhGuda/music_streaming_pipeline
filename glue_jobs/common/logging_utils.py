"""Shared structured logging helpers for Glue jobs."""

from __future__ import annotations

import json
import logging
import sys
import traceback
from datetime import datetime, timezone
from typing import Any


def configure_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """Return a CloudWatch-friendly logger that emits one JSON object per line."""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)

    return logger


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def log_event(
    logger: logging.Logger,
    event: str,
    *,
    level: int = logging.INFO,
    **fields: Any,
) -> None:
    """Write a structured log event with stable top-level fields."""
    payload = {
        "timestamp": _utc_now_iso(),
        "event": event,
        **fields,
    }
    logger.log(level, json.dumps(payload, default=str, sort_keys=True))


def log_exception(
    logger: logging.Logger,
    event: str,
    *,
    exc: BaseException,
    **fields: Any,
) -> None:
    """Write a structured exception event with traceback details."""
    log_event(
        logger,
        event,
        level=logging.ERROR,
        error_type=type(exc).__name__,
        error_message=str(exc),
        traceback="".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
        **fields,
    )
