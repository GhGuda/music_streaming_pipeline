"""Validation utilities for the Glue input-validation job.

This module keeps core validation logic pure/testable. The Glue runtime entrypoint
can call these functions and handle AWS I/O separately.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import logging
import sys
import traceback
from datetime import datetime
from typing import Any

import boto3


def configure_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    _log = logging.getLogger(name)
    _log.setLevel(level)
    _log.propagate = False
    if not _log.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        _log.addHandler(handler)
    return _log


def log_event(logger: logging.Logger, event: str, *, level: int = logging.INFO, **fields) -> None:
    import datetime

    ts = (
        datetime.datetime.now(datetime.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    payload = {"timestamp": ts, "event": event, **fields}
    logger.log(level, json.dumps(payload, default=str, sort_keys=True))


def log_exception(logger: logging.Logger, event: str, *, exc: BaseException, **fields) -> None:
    log_event(
        logger,
        event,
        level=logging.ERROR,
        error_type=type(exc).__name__,
        error_message=str(exc),
        traceback="".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
        **fields,
    )


REQUIRED_COLUMNS = {
    "users": ["user_id", "user_name", "user_age", "user_country", "created_at"],
    "songs": ["track_id", "artists", "track_name", "duration_ms", "track_genre"],
    "streams": ["user_id", "track_id", "listen_time"],
}

s3 = boto3.client("s3")
logger = configure_logger("validate-inputs")


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


def _head_object(bucket: str, key: str) -> bool:
    """Return True if the object exists, False on 404."""
    from botocore.exceptions import ClientError

    try:
        s3.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if code in ("404", "NoSuchKey", "NotFound") or status == 404:
            return False
        raise ValueError(
            f"head_object failed for s3://{bucket}/{key}: " f"{code or 'Unknown'} (http {status})"
        ) from exc


def _read_csv_rows(bucket: str, key: str) -> list[dict[str, Any]]:
    obj = s3.get_object(Bucket=bucket, Key=key)
    body = obj["Body"].read().decode("utf-8")
    reader = csv.DictReader(io.StringIO(body))
    return list(reader)


def _write_result(bucket: str, key: str, payload: dict[str, Any]) -> None:
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(payload).encode("utf-8"),
        ContentType="application/json",
        ServerSideEncryption="aws:kms",
    )


def _parse_args(argv: list[str]) -> dict[str, str]:
    try:
        from awsglue.utils import getResolvedOptions  # type: ignore

        args = getResolvedOptions(argv, ["event", "scripts_bucket", "execution_id"])
        return {
            "event": args["event"],
            "scripts_bucket": args["scripts_bucket"],
            "execution_id": args["execution_id"],
        }
    except Exception:
        parser = argparse.ArgumentParser()
        parser.add_argument("--event", required=True)
        parser.add_argument("--scripts_bucket", required=True)
        parser.add_argument("--execution_id", required=True)
        ns = parser.parse_args(argv[1:])
        return vars(ns)


def main(argv: list[str] | None = None) -> None:
    import sys

    args = _parse_args(argv or sys.argv)
    event = json.loads(args["event"])
    scripts_bucket = args["scripts_bucket"]
    execution_id = args["execution_id"]
    result_key = f"validation_results/{execution_id}.json"

    raw_bucket = event["detail"]["bucket"]["name"]
    stream_key = event["detail"]["object"]["key"]

    log_event(
        logger,
        "validation_started",
        raw_bucket=raw_bucket,
        stream_key=stream_key,
        scripts_bucket=scripts_bucket,
        execution_id=execution_id,
        result_key=result_key,
    )

    try:
        if not _head_object(raw_bucket, "incoming/users/users.csv"):
            raise FileNotFoundError("users: missing incoming/users/users.csv")
        if not _head_object(raw_bucket, "incoming/songs/songs.csv"):
            raise FileNotFoundError("songs: missing incoming/songs/songs.csv")

        users_rows = _read_csv_rows(raw_bucket, "incoming/users/users.csv")
        songs_rows = _read_csv_rows(raw_bucket, "incoming/songs/songs.csv")
        stream_rows = _read_csv_rows(raw_bucket, stream_key)

        if not users_rows:
            raise ValueError("users: file is empty")
        if not songs_rows:
            raise ValueError("songs: file is empty")

        validate_columns(list(users_rows[0].keys()), "users")
        validate_columns(list(songs_rows[0].keys()), "songs")
        validate_columns(
            list(stream_rows[0].keys()) if stream_rows else REQUIRED_COLUMNS["streams"], "streams"
        )

        stream_dates = validate_stream_rows(stream_rows)
        result = build_validation_result("VALID", "ok", raw_bucket, stream_key, stream_dates)
        log_event(
            logger,
            "validation_succeeded",
            raw_bucket=raw_bucket,
            stream_key=stream_key,
            execution_id=execution_id,
            stream_dates=stream_dates,
            users_rows=len(users_rows),
            songs_rows=len(songs_rows),
            stream_rows=len(stream_rows),
        )
    except Exception as exc:  # noqa: BLE001
        result = build_validation_result("INVALID", str(exc), raw_bucket, stream_key, [])
        log_exception(
            logger,
            "validation_failed",
            exc=exc,
            raw_bucket=raw_bucket,
            stream_key=stream_key,
            execution_id=execution_id,
        )

    _write_result(scripts_bucket, result_key, result)
    log_event(
        logger,
        "validation_result_written",
        scripts_bucket=scripts_bucket,
        result_key=result_key,
        status=result["status"],
        stream_dates=result["stream_dates"],
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
