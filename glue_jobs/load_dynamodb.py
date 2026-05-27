"""Core DynamoDB item-building logic for KPI loader job."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import boto3
from pyspark.sql import SparkSession


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
        "listen_count": int(row["listen_count"]),
        "unique_listeners": int(row["unique_listeners"]),
        "total_listening_time_seconds": float(row["total_listening_time_seconds"]),
        "avg_listening_time_per_user_seconds": float(row["avg_listening_time_per_user_seconds"]),
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
            "rank": int(row["rank"]),
            "track_id": row["track_id"],
            "track_name": row["track_name"],
            "artists": row["artists"],
            "listen_count": int(row["listen_count"]),
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
            "rank": int(row["rank"]),
            "genre": row["genre"],
            "listen_count": int(row["listen_count"]),
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


def main(argv: list[str] | None = None) -> None:
    import sys

    args = _parse_args(argv or sys.argv)
    processed_bucket = args["processed_bucket"]
    table_name = args["dynamodb_table"]
    stream_dates: list[str] = json.loads(args["stream_dates"])

    spark = SparkSession.builder.appName("load-dynamodb").getOrCreate()
    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(table_name)

    daily_df = spark.read.parquet(f"s3://{processed_bucket}/gold/daily_genre_kpis/")
    top_songs_df = spark.read.parquet(f"s3://{processed_bucket}/gold/top_songs_by_genre/")
    top_genres_df = spark.read.parquet(f"s3://{processed_bucket}/gold/top_genres/")

    if stream_dates:
        daily_df = daily_df.filter(daily_df.stream_date.isin(stream_dates))
        top_songs_df = top_songs_df.filter(top_songs_df.stream_date.isin(stream_dates))
        top_genres_df = top_genres_df.filter(top_genres_df.stream_date.isin(stream_dates))

    daily_rows = [r.asDict(recursive=True) for r in daily_df.collect()]
    top_songs_rows = [r.asDict(recursive=True) for r in top_songs_df.collect()]
    top_genres_rows = [r.asDict(recursive=True) for r in top_genres_df.collect()]

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

    spark.stop()


if __name__ == "__main__":
    main()
