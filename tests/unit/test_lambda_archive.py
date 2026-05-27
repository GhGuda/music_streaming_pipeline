import importlib
from unittest.mock import MagicMock

failure_handler = importlib.import_module("lambda.archive_failure.handler")
success_handler = importlib.import_module("lambda.archive_success.handler")


def test_archive_success_handler(monkeypatch) -> None:
    fake_s3 = MagicMock()
    monkeypatch.setattr(success_handler, "s3", fake_s3)
    monkeypatch.setenv("ARCHIVE_BUCKET", "archive-bucket")

    out = success_handler.handler(
        {"raw_bucket": "raw-bucket", "stream_key": "incoming/streams/streams1.csv"},
        None,
    )

    fake_s3.copy_object.assert_called_once()
    fake_s3.delete_object.assert_called_once_with(
        Bucket="raw-bucket",
        Key="incoming/streams/streams1.csv",
    )
    assert out["archived_to"].startswith("s3://archive-bucket/processed/")
    assert out["archived_to"].endswith("/streams1.csv")


def test_archive_failure_handler(monkeypatch) -> None:
    fake_s3 = MagicMock()
    monkeypatch.setattr(failure_handler, "s3", fake_s3)
    monkeypatch.setenv("ARCHIVE_BUCKET", "archive-bucket")

    out = failure_handler.handler(
        {
            "raw_bucket": "raw-bucket",
            "stream_key": "incoming/streams/streams_bad.csv",
            "error": {"status": "INVALID", "reason": "missing track_id"},
        },
        None,
    )

    fake_s3.copy_object.assert_called_once()
    fake_s3.put_object.assert_called_once()
    fake_s3.delete_object.assert_called_once_with(
        Bucket="raw-bucket",
        Key="incoming/streams/streams_bad.csv",
    )
    assert out["archived_to"].startswith("s3://archive-bucket/failed/")
    assert out["error_json"].endswith("/streams_bad.csv.error.json")
