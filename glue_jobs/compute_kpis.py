"""Core KPI computation logic for the Glue PySpark job."""

from collections import defaultdict

from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.window import Window


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
