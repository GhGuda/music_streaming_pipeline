"""Archive a failed stream file and write an adjacent error JSON document.

Idempotent: if the source file is already gone (e.g. a previous failure-path run
archived it, or it was never written), still drop the error JSON next to where
it would have been, and return success. This keeps the state machine from
double-failing when transient retries duplicate the call.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.exceptions import ClientError

log = logging.getLogger()
log.setLevel(logging.INFO)

s3 = boto3.client("s3")


def _archive_prefix(now_utc: datetime | None = None) -> str:
    ts = now_utc or datetime.now(timezone.utc)
    return ts.strftime("failed/%Y/%m/%d")


def _source_exists(bucket: str, key: str) -> bool:
    try:
        s3.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
            return False
        raise


def handler(event: dict[str, Any], _context: Any) -> dict[str, str]:
    archive_bucket = os.environ["ARCHIVE_BUCKET"]
    src_bucket = event["raw_bucket"]
    src_key = event["stream_key"]
    error = event.get("error", {})

    filename = src_key.split("/")[-1]
    base_prefix = _archive_prefix()
    dst_key = f"{base_prefix}/{filename}"
    error_key = f"{base_prefix}/{filename}.error.json"

    # Always drop the error JSON — debuggers need it even if the source is gone.
    s3.put_object(
        Bucket=archive_bucket,
        Key=error_key,
        Body=json.dumps(error, default=str).encode("utf-8"),
        ContentType="application/json",
        ServerSideEncryption="aws:kms",
    )

    # If the source already moved (e.g. a parallel execution beat us), skip the copy.
    if not _source_exists(src_bucket, src_key):
        log.info(
            'archive_failure: source already absent, error_json only'
            ' src=s3://%s/%s dst=s3://%s/%s',
            src_bucket, src_key, archive_bucket, dst_key,
        )
        return {
            "archived_to": f"s3://{archive_bucket}/{dst_key}",
            "error_json": f"s3://{archive_bucket}/{error_key}",
            "status": "already_archived",
        }

    s3.copy_object(
        Bucket=archive_bucket,
        Key=dst_key,
        CopySource={"Bucket": src_bucket, "Key": src_key},
        ServerSideEncryption="aws:kms",
    )
    s3.delete_object(Bucket=src_bucket, Key=src_key)
    log.info(
        'archive_failure: moved src=s3://%s/%s dst=s3://%s/%s',
        src_bucket, src_key, archive_bucket, dst_key,
    )

    return {
        "archived_to": f"s3://{archive_bucket}/{dst_key}",
        "error_json": f"s3://{archive_bucket}/{error_key}",
        "status": "archived",
    }
