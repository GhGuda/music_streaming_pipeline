from glue_jobs.compute_kpis import compute_daily_genre_kpis_records


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
