"""Archive a successfully-processed stream file from raw to archive bucket."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import boto3

s3 = boto3.client("s3")


def _archive_prefix(now_utc: datetime | None = None) -> str:
    ts = now_utc or datetime.now(timezone.utc)
    return ts.strftime("processed/%Y/%m/%d")


def handler(event: dict[str, Any], _context: Any) -> dict[str, str]:
    archive_bucket = os.environ["ARCHIVE_BUCKET"]
    src_bucket = event["raw_bucket"]
    src_key = event["stream_key"]

    filename = src_key.split("/")[-1]
    dst_key = f"{_archive_prefix()}/{filename}"

    s3.copy_object(
        Bucket=archive_bucket,
        Key=dst_key,
        CopySource={"Bucket": src_bucket, "Key": src_key},
        ServerSideEncryption="aws:kms",
    )
    s3.delete_object(Bucket=src_bucket, Key=src_key)

    return {"archived_to": f"s3://{archive_bucket}/{dst_key}"}
