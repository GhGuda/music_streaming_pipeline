"""Archive a successfully-processed stream file from raw to archive bucket.

Idempotent: if the source file is already gone (e.g. a previous run archived
it), or the destination already exists, treat the operation as a no-op success
rather than a failure. This makes the Lambda safe to retry and tolerant of
duplicate executions caused by S3 versioning + EventBridge.
"""

from __future__ import annotations

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
    return ts.strftime("processed/%Y/%m/%d")


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

    filename = src_key.split("/")[-1]
    dst_key = f"{_archive_prefix()}/{filename}"

    # Idempotency: if the source isn't there, somebody else already moved it.
    if not _source_exists(src_bucket, src_key):
        log.info(
            'archive_success: source already absent, no-op'
            ' src=s3://%s/%s dst=s3://%s/%s',
            src_bucket, src_key, archive_bucket, dst_key,
        )
        return {
            "archived_to": f"s3://{archive_bucket}/{dst_key}",
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
        'archive_success: moved src=s3://%s/%s dst=s3://%s/%s',
        src_bucket, src_key, archive_bucket, dst_key,
    )

    return {
        "archived_to": f"s3://{archive_bucket}/{dst_key}",
        "status": "archived",
    }
