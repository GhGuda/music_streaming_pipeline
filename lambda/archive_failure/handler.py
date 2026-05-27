"""Archive a failed stream file and write an adjacent error JSON document."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

import boto3

s3 = boto3.client("s3")


def _archive_prefix(now_utc: datetime | None = None) -> str:
    ts = now_utc or datetime.now(timezone.utc)
    return ts.strftime("failed/%Y/%m/%d")


def handler(event: dict[str, Any], _context: Any) -> dict[str, str]:
    archive_bucket = os.environ["ARCHIVE_BUCKET"]
    src_bucket = event["raw_bucket"]
    src_key = event["stream_key"]
    error = event.get("error", {})

    filename = src_key.split("/")[-1]
    base_prefix = _archive_prefix()
    dst_key = f"{base_prefix}/{filename}"
    error_key = f"{base_prefix}/{filename}.error.json"

    s3.copy_object(
        Bucket=archive_bucket,
        Key=dst_key,
        CopySource={"Bucket": src_bucket, "Key": src_key},
        ServerSideEncryption="aws:kms",
    )
    s3.put_object(
        Bucket=archive_bucket,
        Key=error_key,
        Body=json.dumps(error).encode("utf-8"),
        ContentType="application/json",
        ServerSideEncryption="aws:kms",
    )
    s3.delete_object(Bucket=src_bucket, Key=src_key)

    return {
        "archived_to": f"s3://{archive_bucket}/{dst_key}",
        "error_json": f"s3://{archive_bucket}/{error_key}",
    }
