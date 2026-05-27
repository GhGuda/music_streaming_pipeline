"""Core KPI computation logic for the Glue PySpark job."""

from collections import defaultdict

from pyspark.sql import DataFrame
from pyspark.sql import functions as F


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
    )

    return streams.join(songs, on="track_id", how="inner")


def compute_daily_genre_kpis(enriched_df: DataFrame) -> DataFrame:
    """Compute daily genre KPI aggregates."""
    return (
        enriched_df.groupBy("stream_date", "genre")
        .agg(
            F.count("*").alias("listen_count"),
            F.countDistinct("user_id").alias("unique_listeners"),
            F.sum("effective_listen_seconds").alias("total_listening_time_seconds"),
        )
        .withColumn(
            "avg_listening_time_per_user_seconds",
            F.when(
                F.col("unique_listeners") > 0,
                F.col("total_listening_time_seconds") / F.col("unique_listeners"),
            ).otherwise(F.lit(0.0)),
        )
    )


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
