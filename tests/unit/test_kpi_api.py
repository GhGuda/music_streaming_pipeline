import importlib
import sys
from decimal import Decimal
from unittest.mock import MagicMock


def _load_handler(monkeypatch):
    monkeypatch.setenv("DYNAMODB_TABLE", "music-streaming-dev-kpis")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    sys.modules.pop("lambda.kpi_api.handler", None)
    module = importlib.import_module("lambda.kpi_api.handler")
    return module


def test_kpi_api_daily_route(monkeypatch) -> None:
    module = _load_handler(monkeypatch)
    fake_table = MagicMock()
    fake_table.query.return_value = {
        "Items": [
            {
                "pk": "DATE#2024-06-25",
                "sk": "GENRE#afrobeat",
                "record_type": "DAILY_GENRE_KPI",
                "date": "2024-06-25",
                "genre": "afrobeat",
                "listen_count": Decimal("10"),
            }
        ]
    }
    monkeypatch.setattr(module, "table", fake_table)

    out = module.handler(
        {"rawPath": "/daily", "queryStringParameters": {"date": "2024-06-25"}},
        None,
    )

    assert out["statusCode"] == 200
    assert '"genre": "afrobeat"' in out["body"]
    assert '"listen_count": 10' in out["body"]


def test_kpi_api_requires_date(monkeypatch) -> None:
    module = _load_handler(monkeypatch)

    out = module.handler({"rawPath": "/daily", "queryStringParameters": {}}, None)

    assert out["statusCode"] == 400
    assert "date" in out["body"]
