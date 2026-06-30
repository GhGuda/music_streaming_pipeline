"""Read-only KPI API for the dashboard."""

from __future__ import annotations

import json
import os
from decimal import Decimal
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key

TABLE_NAME = os.environ["DYNAMODB_TABLE"]
CORS_ORIGIN = os.environ.get("CORS_ORIGIN", "*")

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        if value % 1 == 0:
            return int(value)
        return float(value)
    return str(value)


def _response(status_code: int, body: Any) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {
            "Access-Control-Allow-Origin": CORS_ORIGIN,
            "Access-Control-Allow-Headers": "content-type",
            "Access-Control-Allow-Methods": "GET,OPTIONS",
            "Content-Type": "application/json",
        },
        "body": json.dumps(body, default=_json_default),
    }


def _query_day(date: str) -> list[dict[str, Any]]:
    response = table.query(KeyConditionExpression=Key("pk").eq(f"DATE#{date}"))
    items = response.get("Items", [])
    while "LastEvaluatedKey" in response:
        response = table.query(
            KeyConditionExpression=Key("pk").eq(f"DATE#{date}"),
            ExclusiveStartKey=response["LastEvaluatedKey"],
        )
        items.extend(response.get("Items", []))
    return items


def _query_dates() -> list[str]:
    dates: set[str] = set()
    scan_kwargs: dict[str, Any] = {
        "ProjectionExpression": "#date",
        "ExpressionAttributeNames": {"#date": "date"},
    }
    response = table.scan(**scan_kwargs)
    dates.update(item["date"] for item in response.get("Items", []) if "date" in item)
    while "LastEvaluatedKey" in response:
        response = table.scan(**scan_kwargs, ExclusiveStartKey=response["LastEvaluatedKey"])
        dates.update(item["date"] for item in response.get("Items", []) if "date" in item)
    return sorted(dates, reverse=True)


def _daily(date: str) -> dict[str, Any]:
    rows = [item for item in _query_day(date) if item.get("record_type") == "DAILY_GENRE_KPI"]
    rows.sort(key=lambda item: (-int(item.get("listen_count", 0)), item.get("genre", "")))
    return {"date": date, "items": rows}


def _top_genres(date: str) -> dict[str, Any]:
    item = table.get_item(Key={"pk": f"DATE#{date}", "sk": "TOP_GENRES"}).get("Item")
    return {"date": date, "item": item}


def _top_songs(date: str, genre: str) -> dict[str, Any]:
    item = table.get_item(Key={"pk": f"DATE#{date}", "sk": f"GENRE#{genre}#TOP_SONGS"}).get("Item")
    return {"date": date, "genre": genre, "item": item}


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    if event.get("requestContext", {}).get("http", {}).get("method") == "OPTIONS":
        return _response(204, {})

    route = event.get("rawPath", "/")
    params = event.get("queryStringParameters") or {}

    try:
        if route == "/dates":
            return _response(200, {"dates": _query_dates()})

        date = params.get("date")
        if not date:
            return _response(400, {"error": "Missing required query parameter: date"})

        if route == "/daily":
            return _response(200, _daily(date))
        if route == "/top-genres":
            return _response(200, _top_genres(date))
        if route == "/top-songs":
            genre = params.get("genre")
            if not genre:
                return _response(400, {"error": "Missing required query parameter: genre"})
            return _response(200, _top_songs(date, genre))

        return _response(404, {"error": "Not found"})
    except Exception as exc:  # noqa: BLE001
        return _response(500, {"error": "Internal server error", "detail": str(exc)})
