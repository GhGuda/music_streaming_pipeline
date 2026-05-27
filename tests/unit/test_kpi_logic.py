from glue_jobs.compute_kpis import (
    compute_daily_genre_kpis_records,
    compute_top_3_songs_by_genre_records,
    compute_top_5_genres_records,
)


def test_daily_genre_kpis() -> None:
    out = compute_daily_genre_kpis_records(
        [
            {
                "stream_date": "2024-06-25",
                "genre": "afrobeat",
                "user_id": "u1",
                "effective_listen_seconds": 200.0,
            },
            {
                "stream_date": "2024-06-25",
                "genre": "afrobeat",
                "user_id": "u2",
                "effective_listen_seconds": 200.0,
            },
            {
                "stream_date": "2024-06-25",
                "genre": "afrobeat",
                "user_id": "u1",
                "effective_listen_seconds": 180.0,
            },
        ]
    )[0]

    assert out["listen_count"] == 3
    assert out["unique_listeners"] == 2
    assert out["total_listening_time_seconds"] == 580.0
    assert out["avg_listening_time_per_user_seconds"] == 290.0


def test_top_3_songs_by_genre() -> None:
    out = compute_top_3_songs_by_genre_records(
        [
            {
                "stream_date": "2024-06-25",
                "genre": "afrobeat",
                "track_id": "t2",
                "track_name": "B",
                "artists": "A2",
            },
            {
                "stream_date": "2024-06-25",
                "genre": "afrobeat",
                "track_id": "t2",
                "track_name": "B",
                "artists": "A2",
            },
            {
                "stream_date": "2024-06-25",
                "genre": "afrobeat",
                "track_id": "t1",
                "track_name": "A",
                "artists": "A1",
            },
            {
                "stream_date": "2024-06-25",
                "genre": "afrobeat",
                "track_id": "t1",
                "track_name": "A",
                "artists": "A1",
            },
            {
                "stream_date": "2024-06-25",
                "genre": "afrobeat",
                "track_id": "t3",
                "track_name": "C",
                "artists": "A3",
            },
            {
                "stream_date": "2024-06-25",
                "genre": "afrobeat",
                "track_id": "t4",
                "track_name": "D",
                "artists": "A4",
            },
        ]
    )

    assert len(out) == 3
    assert out[0]["rank"] == 1 and out[0]["track_id"] == "t1"  # tie-break by track_id asc
    assert out[1]["rank"] == 2 and out[1]["track_id"] == "t2"
    assert out[2]["rank"] == 3 and out[2]["track_id"] == "t3"


def test_top_5_genres_per_day() -> None:
    out = compute_top_5_genres_records(
        [
            {"stream_date": "2024-06-25", "genre": "pop"},
            {"stream_date": "2024-06-25", "genre": "pop"},
            {"stream_date": "2024-06-25", "genre": "afrobeat"},
            {"stream_date": "2024-06-25", "genre": "afrobeat"},
            {"stream_date": "2024-06-25", "genre": "hip-hop"},
            {"stream_date": "2024-06-25", "genre": "gospel"},
            {"stream_date": "2024-06-25", "genre": "jazz"},
            {"stream_date": "2024-06-25", "genre": "rock"},
            {"stream_date": "2024-06-25", "genre": "rock"},
            {"stream_date": "2024-06-25", "genre": "rock"},
        ]
    )

    assert len(out) == 5
    assert out[0]["rank"] == 1 and out[0]["genre"] == "rock"
    assert out[1]["rank"] == 2 and out[1]["genre"] == "afrobeat"  # tie-break alphabetic
    assert out[2]["rank"] == 3 and out[2]["genre"] == "pop"
