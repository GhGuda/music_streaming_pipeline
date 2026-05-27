"""Core DynamoDB item-building logic for KPI loader job."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


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
