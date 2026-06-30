"""Core KPI computation logic for the Glue PySpark job."""

import argparse
import json
import logging
import sys
import traceback
from collections import defaultdict

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.window import Window


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


logger = configure_logger("compute-kpis")


def enrich_streams_with_songs(streams_df: DataFrame, songs_df: DataFrame) -> DataFrame:
    """Join streams to songs and derive stream_date + effective_listen_seconds."""
    streams = (
        streams_df.withColumn("listen_ts", F.to_timestamp("listen_time"))
        .withColumn("stream_date", F.to_date("listen_ts"))
        .select("user_id", "track_id", "listen_time", "stream_date")
    )

    songs = songs_df.select(
        "track_id",
        "track_name",
        "artists",
        F.col("track_genre").alias("genre"),
        (F.col("duration_ms").cast("double") / F.lit(1000.0)).alias("effective_listen_seconds"),
    ).filter(
        # Drop rows where genre is a bare number (CSV column-shift artefact).
        F.col("genre").isNotNull() & ~F.col("genre").rlike(r"^-?\d+(\.\d+)?$")
    )

    return streams.join(songs, on="track_id", how="inner")


def compute_daily_genre_kpis(enriched_df: DataFrame) -> DataFrame:
    """Compute daily genre KPI aggregates."""
    return (
        enriched_df.groupBy("stream_date", "genre")
        .agg(
            F.count("*").alias("listen_count"),
            F.countDistinct("user_id").alias("unique_listeners"),
            F.coalesce(F.sum("effective_listen_seconds"), F.lit(0.0)).alias(
                "total_listening_time_seconds"
            ),
        )
        .withColumn(
            "avg_listening_time_per_user_seconds",
            F.when(
                F.col("unique_listeners") > 0,
                F.col("total_listening_time_seconds") / F.col("unique_listeners"),
            ).otherwise(F.lit(0.0)),
        )
    )


def compute_top_3_songs_by_genre(enriched_df: DataFrame) -> DataFrame:
    """Compute top 3 songs per (stream_date, genre) by listen count."""
    counts = enriched_df.groupBy("stream_date", "genre", "track_id", "track_name", "artists").agg(
        F.count("*").alias("listen_count")
    )
    w = Window.partitionBy("stream_date", "genre").orderBy(
        F.col("listen_count").desc(), F.col("track_id").asc()
    )
    return (
        counts.withColumn("rank", F.row_number().over(w))
        .filter(F.col("rank") <= 3)
        .select("stream_date", "genre", "rank", "track_id", "track_name", "artists", "listen_count")
    )


def compute_top_5_genres(enriched_df: DataFrame) -> DataFrame:
    """Compute top 5 genres per stream_date by listen count."""
    counts = enriched_df.groupBy("stream_date", "genre").agg(F.count("*").alias("listen_count"))
    w = Window.partitionBy("stream_date").orderBy(
        F.col("listen_count").desc(), F.col("genre").asc()
    )
    return (
        counts.withColumn("rank", F.row_number().over(w))
        .filter(F.col("rank") <= 5)
        .select("stream_date", "rank", "genre", "listen_count")
    )


# === Pure-Python equivalents for deterministic unit testing ===


def compute_daily_genre_kpis_records(records: list[dict]) -> list[dict]:
    """Pure-Python equivalent used for lightweight unit testing."""
    grouped: dict[tuple[str, str], dict] = defaultdict(
        lambda: {
            "listen_count": 0,
            "users": set(),
            "total_listening_time_seconds": 0.0,
        }
    )
    for row in records:
        key = (row["stream_date"], row["genre"])
        grouped[key]["listen_count"] += 1
        grouped[key]["users"].add(str(row["user_id"]))
        grouped[key]["total_listening_time_seconds"] += float(row["effective_listen_seconds"])

    out: list[dict] = []
    for (stream_date, genre), agg in sorted(grouped.items()):
        unique_listeners = len(agg["users"])
        total = agg["total_listening_time_seconds"]
        avg = total / unique_listeners if unique_listeners else 0.0
        out.append(
            {
                "stream_date": stream_date,
                "genre": genre,
                "listen_count": agg["listen_count"],
                "unique_listeners": unique_listeners,
                "total_listening_time_seconds": total,
                "avg_listening_time_per_user_seconds": avg,
            }
        )
    return out


def compute_top_3_songs_by_genre_records(records: list[dict]) -> list[dict]:
    """Pure-Python top-3 songs per genre/day helper for deterministic tests."""
    grouped: dict[tuple[str, str, str, str, str], int] = defaultdict(int)
    for row in records:
        key = (
            row["stream_date"],
            row["genre"],
            row["track_id"],
            row["track_name"],
            row["artists"],
        )
        grouped[key] += 1

    by_partition: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for (stream_date, genre, track_id, track_name, artists), count in grouped.items():
        by_partition[(stream_date, genre)].append(
            {
                "stream_date": stream_date,
                "genre": genre,
                "track_id": track_id,
                "track_name": track_name,
                "artists": artists,
                "listen_count": count,
            }
        )

    out: list[dict] = []
    for (stream_date, genre), rows in sorted(by_partition.items()):
        rows_sorted = sorted(rows, key=lambda r: (-r["listen_count"], r["track_id"]))
        for i, row in enumerate(rows_sorted[:3], start=1):
            out.append({**row, "rank": i})
    return out


def compute_top_5_genres_records(records: list[dict]) -> list[dict]:
    """Pure-Python top-5 genres per day helper for deterministic tests."""
    grouped: dict[tuple[str, str], int] = defaultdict(int)
    for row in records:
        grouped[(row["stream_date"], row["genre"])] += 1

    by_day: dict[str, list[dict]] = defaultdict(list)
    for (stream_date, genre), count in grouped.items():
        by_day[stream_date].append(
            {"stream_date": stream_date, "genre": genre, "listen_count": count}
        )

    out: list[dict] = []
    for stream_date, rows in sorted(by_day.items()):
        rows_sorted = sorted(rows, key=lambda r: (-r["listen_count"], r["genre"]))
        for i, row in enumerate(rows_sorted[:5], start=1):
            out.append({**row, "rank": i})
    return out


def _parse_args(argv: list[str]) -> dict[str, str]:
    try:
        from awsglue.utils import getResolvedOptions  # type: ignore

        args = getResolvedOptions(
            argv, ["raw_bucket", "processed_bucket", "stream_key", "stream_dates"]
        )
        return {
            "raw_bucket": args["raw_bucket"],
            "processed_bucket": args["processed_bucket"],
            "stream_key": args["stream_key"],
            "stream_dates": args["stream_dates"],
        }
    except Exception:
        parser = argparse.ArgumentParser()
        parser.add_argument("--raw_bucket", required=True)
        parser.add_argument("--processed_bucket", required=True)
        parser.add_argument("--stream_key", required=True)
        parser.add_argument("--stream_dates", required=True)
        ns = parser.parse_args(argv[1:])
        return vars(ns)


def _silver_path(processed_bucket: str) -> str:
    return f"s3://{processed_bucket}/silver/streams_enriched/"


def _read_existing_silver_for_dates(
    spark: SparkSession, processed_bucket: str, stream_dates: list[str]
) -> DataFrame | None:
    """Read previously-written enriched data for the same dates, if any.

    Returns None on the first run (no silver Parquet has been written yet) or
    if no partitions for the requested dates exist.
    """
    if not stream_dates:
        return None

    try:
        df = (
            spark.read.option("basePath", _silver_path(processed_bucket))
            .parquet(_silver_path(processed_bucket))
            .filter(F.col("stream_date").isin(stream_dates))
        )
        # Touch the catalyst optimiser to force path validation. If the path
        # doesn't exist, AnalysisException is raised here rather than later.
        _ = df.schema  # noqa: F841
        return df
    except Exception:
        # First run, or none of the requested partitions exist yet.
        return None


def main(argv: list[str] | None = None) -> None:
    import sys

    args = _parse_args(argv or sys.argv)
    raw_bucket = args["raw_bucket"]
    processed_bucket = args["processed_bucket"]
    stream_key = args["stream_key"]
    stream_dates: list[str] = json.loads(args["stream_dates"])

    log_event(
        logger,
        "compute_started",
        raw_bucket=raw_bucket,
        processed_bucket=processed_bucket,
        stream_key=stream_key,
        stream_dates=stream_dates,
    )

    spark = SparkSession.builder.appName("compute-kpis").getOrCreate()
    try:
        # Critical: only overwrite the partitions we're writing to. Without this,
        # mode("overwrite") would wipe every existing partition.
        spark.conf.set("spark.sql.sources.partitionOverwriteMode", "dynamic")

        streams_path = f"s3://{raw_bucket}/{stream_key}"
        songs_path = f"s3://{raw_bucket}/incoming/songs/songs.csv"

        # 1. Enrich the NEW stream file (the trigger).
        new_streams = spark.read.option("header", "true").csv(streams_path)
        songs_df = spark.read.option("header", "true").csv(songs_path)
        new_enriched = enrich_streams_with_songs(new_streams, songs_df)
        if stream_dates:
            new_enriched = new_enriched.filter(F.col("stream_date").isin(stream_dates))

        # 2. Aggregate-on-read: union with the EXISTING silver for the same dates,
        #    if any. This makes the pipeline accumulate across multiple stream
        #    files arriving for the same day (instead of last-write-wins).
        existing = _read_existing_silver_for_dates(spark, processed_bucket, stream_dates)

        if existing is not None:
            # Materialize existing silver into Spark cache BEFORE the write step.
            # partitionOverwriteMode=dynamic deletes source partition files during
            # job commit; tasks still reading from a lazy `existing` DataFrame see
            # "File not present on S3" when their source files disappear mid-run.
            # .cache() + .count() forces a full read into memory first.
            existing.cache()
            existing.count()
            # Align columns so union behaves deterministically across schema-evolution.
            cols = new_enriched.columns
            existing_aligned = existing.select(*cols)
            combined = new_enriched.unionByName(existing_aligned, allowMissingColumns=False)
        else:
            combined = new_enriched

        # 3. Dedup on the natural event key. Re-uploading the same file or
        #    overlapping uploads for the same (user, track, time) collapse to one.
        enriched = combined.dropDuplicates(["user_id", "track_id", "listen_time"])

        # 4. Re-aggregate KPIs from the FULL set of events for the touched dates.
        daily = compute_daily_genre_kpis(enriched)
        top_songs = compute_top_3_songs_by_genre(enriched)
        top_genres = compute_top_5_genres(enriched)

        # 5. Write back. partitionOverwriteMode=dynamic ensures only the touched
        #    date partitions are replaced; older dates are left alone.
        (
            enriched.write.mode("overwrite")
            .partitionBy("stream_date")
            .parquet(_silver_path(processed_bucket))
        )
        (
            daily.write.mode("overwrite")
            .partitionBy("stream_date")
            .parquet(f"s3://{processed_bucket}/gold/daily_genre_kpis/")
        )
        (
            top_songs.write.mode("overwrite")
            .partitionBy("stream_date")
            .parquet(f"s3://{processed_bucket}/gold/top_songs_by_genre/")
        )
        (
            top_genres.write.mode("overwrite")
            .partitionBy("stream_date")
            .parquet(f"s3://{processed_bucket}/gold/top_genres/")
        )

        log_event(
            logger,
            "compute_succeeded",
            processed_bucket=processed_bucket,
            stream_key=stream_key,
            stream_dates=stream_dates,
            used_existing_silver=existing is not None,
        )
    except Exception as exc:
        log_exception(
            logger,
            "compute_failed",
            exc=exc,
            raw_bucket=raw_bucket,
            processed_bucket=processed_bucket,
            stream_key=stream_key,
            stream_dates=stream_dates,
        )
        raise
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
