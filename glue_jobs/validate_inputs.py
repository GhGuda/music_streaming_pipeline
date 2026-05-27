"""Validation utilities for the Glue input-validation job.

This module keeps core validation logic pure/testable. The Glue runtime entrypoint
can call these functions and handle AWS I/O separately.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
from datetime import datetime
from typing import Any

import boto3

REQUIRED_COLUMNS = {
    "users": ["user_id", "user_name", "user_age", "user_country", "created_at"],
    "songs": ["track_id", "artists", "track_name", "duration_ms", "track_genre"],
    "streams": ["user_id", "track_id", "listen_time"],
}

s3 = boto3.client("s3")


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
    try:
        s3.head_object(Bucket=bucket, Key=key)
        return True
    except Exception:
        return False


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
    except Exception as exc:  # noqa: BLE001
        result = build_validation_result("INVALID", str(exc), raw_bucket, stream_key, [])

    _write_result(scripts_bucket, result_key, result)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
