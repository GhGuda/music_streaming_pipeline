import pytest

from glue_jobs.validate_inputs import (
    build_validation_result,
    validate_columns,
    validate_stream_rows,
)


def test_validate_columns_passes_for_streams() -> None:
    validate_columns(["user_id", "track_id", "listen_time"], "streams")


def test_validate_columns_fails_on_missing() -> None:
    with pytest.raises(ValueError, match="missing required columns"):
        validate_columns(["user_id", "listen_time"], "streams")


def test_validate_stream_rows_extracts_dates() -> None:
    rows = [
        {"user_id": "1", "track_id": "trk_1", "listen_time": "2024-06-25 10:00:00"},
        {"user_id": "2", "track_id": "trk_2", "listen_time": "2024-06-25 11:30:00"},
        {"user_id": "3", "track_id": "trk_3", "listen_time": "2024-06-26 00:05:12"},
    ]
    assert validate_stream_rows(rows) == ["2024-06-25", "2024-06-26"]


def test_validate_stream_rows_rejects_invalid_timestamp() -> None:
    rows = [{"user_id": "1", "track_id": "trk_1", "listen_time": "bad-ts"}]
    with pytest.raises(ValueError, match="invalid listen_time"):
        validate_stream_rows(rows)


def test_build_validation_result_defaults_stream_dates() -> None:
    payload = build_validation_result(
        status="VALID",
        reason="ok",
        raw_bucket="music-streaming-dev-raw",
        stream_key="incoming/streams/streams1.csv",
    )
    assert payload["status"] == "VALID"
    assert payload["stream_dates"] == []
