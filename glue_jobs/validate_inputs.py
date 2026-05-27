"""Validation utilities for the Glue input-validation job.

This module keeps core validation logic pure/testable. The Glue runtime entrypoint
can call these functions and handle AWS I/O separately.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

REQUIRED_COLUMNS = {
    "users": ["user_id", "user_name", "user_age", "user_country", "created_at"],
    "songs": ["track_id", "artists", "track_name", "duration_ms", "track_genre"],
    "streams": ["user_id", "track_id", "listen_time"],
}


def validate_columns(columns: list[str], dataset_name: str) -> None:
    """Raise ValueError if required columns are missing for a dataset."""
    required = REQUIRED_COLUMNS[dataset_name]
    missing = [col for col in required if col not in columns]
    if missing:
        raise ValueError(f"{dataset_name}: missing required columns {missing}")


def _parse_listen_time(value: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError as exc:
        raise ValueError(f"streams: invalid listen_time '{value}'") from exc


def validate_stream_rows(rows: list[dict[str, Any]]) -> list[str]:
    """Validate stream rows and return sorted unique stream dates (YYYY-MM-DD)."""
    if not rows:
        raise ValueError("streams: file is empty")

    dates: set[str] = set()
    for row in rows:
        user_id = str(row.get("user_id", "")).strip()
        track_id = str(row.get("track_id", "")).strip()
        listen_time = str(row.get("listen_time", "")).strip()

        if not user_id:
            raise ValueError("streams: null user_id")
        if not track_id:
            raise ValueError("streams: null track_id")
        parsed = _parse_listen_time(listen_time)
        dates.add(parsed.strftime("%Y-%m-%d"))

    return sorted(dates)


def build_validation_result(
    status: str,
    reason: str,
    raw_bucket: str,
    stream_key: str,
    stream_dates: list[str] | None = None,
) -> dict[str, Any]:
    """Build the Step Functions-compatible validation result payload."""
    return {
        "status": status,
        "reason": reason,
        "raw_bucket": raw_bucket,
        "stream_key": stream_key,
        "stream_dates": stream_dates or [],
    }
