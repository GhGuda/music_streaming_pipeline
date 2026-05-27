from glue_jobs.load_dynamodb import (
    build_daily_genre_kpi_item,
    build_top_3_songs_item,
    build_top_5_genres_item,
)


def test_build_daily_genre_kpi_item_shape() -> None:
    item = build_daily_genre_kpi_item(
        {
            "stream_date": "2024-06-25",
            "genre": "afrobeat",
            "listen_count": 10,
            "unique_listeners": 4,
            "total_listening_time_seconds": 1000.0,
            "avg_listening_time_per_user_seconds": 250.0,
        }
    )
    assert item["pk"] == "DATE#2024-06-25"
    assert item["sk"] == "GENRE#afrobeat"
    assert item["record_type"] == "DAILY_GENRE_KPI"
    assert item["gsi1pk"] == "GENRE#afrobeat"
    assert item["gsi1sk"] == "DATE#2024-06-25"


def test_build_top_3_songs_item_shape() -> None:
    item = build_top_3_songs_item(
        "2024-06-25",
        "afrobeat",
        [
            {
                "rank": 2,
                "track_id": "t2",
                "track_name": "Song B",
                "artists": "Artist B",
                "listen_count": 7,
            },
            {
                "rank": 1,
                "track_id": "t1",
                "track_name": "Song A",
                "artists": "Artist A",
                "listen_count": 9,
            },
            {
                "rank": 3,
                "track_id": "t3",
                "track_name": "Song C",
                "artists": "Artist C",
                "listen_count": 6,
            },
        ],
    )
    assert item["pk"] == "DATE#2024-06-25"
    assert item["sk"] == "GENRE#afrobeat#TOP_SONGS"
    assert item["record_type"] == "TOP_3_SONGS_BY_GENRE"
    assert [x["rank"] for x in item["top_songs"]] == [1, 2, 3]


def test_build_top_5_genres_item_shape() -> None:
    item = build_top_5_genres_item(
        "2024-06-25",
        [
            {"rank": 1, "genre": "rock", "listen_count": 15},
            {"rank": 2, "genre": "pop", "listen_count": 13},
            {"rank": 3, "genre": "afrobeat", "listen_count": 12},
            {"rank": 4, "genre": "hip-hop", "listen_count": 11},
            {"rank": 5, "genre": "jazz", "listen_count": 9},
            {"rank": 6, "genre": "gospel", "listen_count": 8},
        ],
    )
    assert item["pk"] == "DATE#2024-06-25"
    assert item["sk"] == "TOP_GENRES"
    assert item["record_type"] == "TOP_5_GENRES"
    assert len(item["top_genres"]) == 5
    assert item["top_genres"][0]["genre"] == "rock"
