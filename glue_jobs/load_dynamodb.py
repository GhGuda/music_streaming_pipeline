"""Core DynamoDB item-building logic for KPI loader job.

Runs as an AWS Glue Python Shell job. Python Shell has no Spark / JVM, so we
read the gold Parquet outputs with pyarrow and load DynamoDB via boto3.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import traceback
from datetime import datetime, timezone
from decimal import Decimal
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


logger = configure_logger("load-dynamodb")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_daily_genre_kpi_item(row: dict[str, Any]) -> dict[str, Any]:
    """Build one DAILY_GENRE_KPI item from aggregated KPI row."""
    date = row["stream_date"]
    genre = row["genre"]
    return {
        "pk": f"DATE#{date}",
        "sk": f"GENRE#{genre}",
        "record_type": "DAILY_GENRE_KPI",
        "date": date,
        "genre": genre,
        "listen_count": int(row["listen_count"] or 0),
        "unique_listeners": int(row["unique_listeners"] or 0),
        "total_listening_time_seconds": float(row["total_listening_time_seconds"] or 0.0),
        "avg_listening_time_per_user_seconds": float(
            row["avg_listening_time_per_user_seconds"] or 0.0
        ),
        "gsi1pk": f"GENRE#{genre}",
        "gsi1sk": f"DATE#{date}",
        "updated_at": _utc_now_iso(),
    }


def build_top_3_songs_item(
    stream_date: str, genre: str, ranked_rows: list[dict[str, Any]]
) -> dict[str, Any]:
    """Build one TOP_3_SONGS_BY_GENRE item for a date+genre partition."""
    top_songs = [
        {
            "rank": int(row["rank"] or 0),
            "track_id": row["track_id"],
            "track_name": row["track_name"],
            "artists": row["artists"],
            "listen_count": int(row["listen_count"] or 0),
        }
        for row in sorted(ranked_rows, key=lambda r: r["rank"])[:3]
    ]
    return {
        "pk": f"DATE#{stream_date}",
        "sk": f"GENRE#{genre}#TOP_SONGS",
        "record_type": "TOP_3_SONGS_BY_GENRE",
        "date": stream_date,
        "genre": genre,
        "top_songs": top_songs,
        "updated_at": _utc_now_iso(),
    }


def build_top_5_genres_item(stream_date: str, ranked_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Build one TOP_5_GENRES item for a given date."""
    top_genres = [
        {
            "rank": int(row["rank"] or 0),
            "genre": row["genre"],
            "listen_count": int(row["listen_count"] or 0),
        }
        for row in sorted(ranked_rows, key=lambda r: r["rank"])[:5]
    ]
    return {
        "pk": f"DATE#{stream_date}",
        "sk": "TOP_GENRES",
        "record_type": "TOP_5_GENRES",
        "date": stream_date,
        "top_genres": top_genres,
        "updated_at": _utc_now_iso(),
    }


def _parse_args(argv: list[str]) -> dict[str, str]:
    try:
        from awsglue.utils import getResolvedOptions  # type: ignore

        args = getResolvedOptions(argv, ["processed_bucket", "dynamodb_table", "stream_dates"])
        return {
            "processed_bucket": args["processed_bucket"],
            "dynamodb_table": args["dynamodb_table"],
            "stream_dates": args["stream_dates"],
        }
    except Exception:
        parser = argparse.ArgumentParser()
        parser.add_argument("--processed_bucket", required=True)
        parser.add_argument("--dynamodb_table", required=True)
        parser.add_argument("--stream_dates", required=True)
        ns = parser.parse_args(argv[1:])
        return vars(ns)


def _to_dynamo_types(value: Any) -> Any:
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, list):
        return [_to_dynamo_types(v) for v in value]
    if isinstance(value, dict):
        return {k: _to_dynamo_types(v) for k, v in value.items()}
    return value


def _read_partition_rows(base_uri: str, stream_dates: list[str]) -> list[dict[str, Any]]:
    """Read Parquet partitions for the given stream_dates and return list-of-dicts.

    Uses pyarrow.dataset so partition discovery materialises the `stream_date`
    column (which is stored in the path, not the file body) into each row.
    """
    import pyarrow.dataset as ds  # imported lazily so unit tests don't need pyarrow

    if not stream_dates:
        # No filter given -> read everything. Acceptable as a safety fallback.
        ds_obj = ds.dataset(base_uri, format="parquet", partitioning="hive")
        return ds_obj.to_table().to_pylist()

    # Read only the directories we care about; "hive" partitioning recovers stream_date.
    paths = [f"{base_uri.rstrip('/')}/stream_date={d}/" for d in stream_dates]
    rows: list[dict[str, Any]] = []
    for path in paths:
        try:
            ds_obj = ds.dataset(path, format="parquet")
            t = ds_obj.to_table().to_pylist()
        except FileNotFoundError:
            # Partition not yet written for this date; skip.
            continue
        # pyarrow doesn't restore the partition column when given a leaf path,
        # so attach it explicitly from the stream_dates list.
        # We can deduce which date this batch belongs to from the path.
        sd = path.rstrip("/").rsplit("=", 1)[-1]
        for r in t:
            r.setdefault("stream_date", sd)
        rows.extend(t)
    return rows


def main(argv: list[str] | None = None) -> None:
    import sys

    args = _parse_args(argv or sys.argv)
    processed_bucket = args["processed_bucket"]
    table_name = args["dynamodb_table"]
    stream_dates: list[str] = json.loads(args["stream_dates"])

    log_event(
        logger,
        "load_started",
        processed_bucket=processed_bucket,
        dynamodb_table=table_name,
        stream_dates=stream_dates,
    )

    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(table_name)

    try:
        base = f"s3://{processed_bucket}/gold"
        daily_rows = _read_partition_rows(f"{base}/daily_genre_kpis", stream_dates)
        top_songs_rows = _read_partition_rows(f"{base}/top_songs_by_genre", stream_dates)
        top_genres_rows = _read_partition_rows(f"{base}/top_genres", stream_dates)

        items: list[dict[str, Any]] = []
        items.extend(build_daily_genre_kpi_item(r) for r in daily_rows)

        songs_grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for row in top_songs_rows:
            key = (row["stream_date"], row["genre"])
            songs_grouped.setdefault(key, []).append(row)
        for (stream_date, genre), rows in songs_grouped.items():
            items.append(build_top_3_songs_item(stream_date, genre, rows))

        genres_grouped: dict[str, list[dict[str, Any]]] = {}
        for row in top_genres_rows:
            genres_grouped.setdefault(row["stream_date"], []).append(row)
        for stream_date, rows in genres_grouped.items():
            items.append(build_top_5_genres_item(stream_date, rows))

        with table.batch_writer(overwrite_by_pkeys=["pk", "sk"]) as batch:
            for item in items:
                batch.put_item(Item=_to_dynamo_types(item))

        result = {"items_written": len(items), "stream_dates": stream_dates}
        log_event(
            logger,
            "load_succeeded",
            processed_bucket=processed_bucket,
            dynamodb_table=table_name,
            stream_dates=stream_dates,
            daily_genre_rows=len(daily_rows),
            top_songs_rows=len(top_songs_rows),
            top_genres_rows=len(top_genres_rows),
            items_written=len(items),
        )
        print(json.dumps(result))
    except Exception as exc:
        log_exception(
            logger,
            "load_failed",
            exc=exc,
            processed_bucket=processed_bucket,
            dynamodb_table=table_name,
            stream_dates=stream_dates,
        )
        raise


if __name__ == "__main__":
    main()
