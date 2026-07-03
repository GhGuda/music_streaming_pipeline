# DynamoDB Query Reference

This document is the operational reference for querying the music-streaming KPI table. It maps each business question to a concrete `aws dynamodb` (or `boto3`) call that costs as little as possible.

> The KPI table uses a single-table design with composite keys: `pk` = partition key, `sk` = sort key. There is one optional Global Secondary Index, `gsi1` (hash `gsi1pk`, range `gsi1sk`), used for cross-day genre lookups.

## Setup

All examples assume these environment variables. Fill them once per shell:

```bash
export TABLE=$(terraform -chdir=infra/envs/dev output -raw dynamodb_table_name)
export REGION=$(aws configure get region)
```

Example: `music-streaming-dev-kpis`.

## Item Catalogue

| `record_type` | `pk` | `sk` | Source job |
|---|---|---|---|
| `DAILY_GENRE_KPI` | `DATE#<yyyy-mm-dd>` | `GENRE#<genre>` | `load_dynamodb.py` |
| `TOP_3_SONGS_BY_GENRE` | `DATE#<yyyy-mm-dd>` | `GENRE#<genre>#TOP_SONGS` | `load_dynamodb.py` |
| `TOP_5_GENRES` | `DATE#<yyyy-mm-dd>` | `TOP_GENRES` | `load_dynamodb.py` |

All per-genre items also carry `gsi1pk = GENRE#<genre>` and `gsi1sk = DATE#<yyyy-mm-dd>`, enabling efficient cross-day genre queries via `gsi1`.

## 1. Single-day queries (cheapest — direct PK)

### 1.1 Get every KPI item for one day

Returns daily genre KPIs **and** the top songs records **and** the top genres record in one call.

```bash
aws dynamodb query --table-name "$TABLE" \
  --key-condition-expression "pk = :pk" \
  --expression-attribute-values '{":pk":{"S":"DATE#2024-06-25"}}'
```

Filtered by record type (server-side filter — still consumes the same RCU but cheaper to parse):

```bash
aws dynamodb query --table-name "$TABLE" \
  --key-condition-expression "pk = :pk" \
  --filter-expression "record_type = :rt" \
  --expression-attribute-values '{
    ":pk":{"S":"DATE#2024-06-25"},
    ":rt":{"S":"DAILY_GENRE_KPI"}
  }'
```

### 1.2 Get the daily KPI for one genre on one day

```bash
aws dynamodb get-item --table-name "$TABLE" \
  --key '{
    "pk":{"S":"DATE#2024-06-25"},
    "sk":{"S":"GENRE#afrobeat"}
  }'
```

### 1.3 Get the top 3 songs for one (date, genre)

```bash
aws dynamodb get-item --table-name "$TABLE" \
  --key '{
    "pk":{"S":"DATE#2024-06-25"},
    "sk":{"S":"GENRE#afrobeat#TOP_SONGS"}
  }'
```

### 1.4 Get the top 5 genres for one day

```bash
aws dynamodb get-item --table-name "$TABLE" \
  --key '{
    "pk":{"S":"DATE#2024-06-25"},
    "sk":{"S":"TOP_GENRES"}
  }'
```

## 2. Sort-key prefix queries (one day, narrower slice)

### 2.1 Only the daily-genre items for a day (skip the TOP_SONGS / TOP_GENRES rows)

```bash
aws dynamodb query --table-name "$TABLE" \
  --key-condition-expression "pk = :pk AND begins_with(sk, :prefix)" \
  --expression-attribute-values '{
    ":pk":{"S":"DATE#2024-06-25"},
    ":prefix":{"S":"GENRE#"}
  }'
```

This also pulls the `#TOP_SONGS` rows because they start with `GENRE#`. If you want pure daily-genre items only, add `--filter-expression "record_type = :rt"`.

### 2.2 Daily-genre and top-songs items for a single genre on a single day

Use `BETWEEN` on `sk` to constrain to the prefix range:

```bash
aws dynamodb query --table-name "$TABLE" \
  --key-condition-expression "pk = :pk AND sk BETWEEN :lo AND :hi" \
  --expression-attribute-values '{
    ":pk":{"S":"DATE#2024-06-25"},
    ":lo":{"S":"GENRE#afrobeat"},
    ":hi":{"S":"GENRE#afrobeat#~"}
  }'
```

This returns both `GENRE#afrobeat` and `GENRE#afrobeat#TOP_SONGS` — the canonical "everything I know about afrobeat on this day".

## 3. Cross-day genre queries (via GSI1)

### 3.1 One genre across a date range

```bash
aws dynamodb query --table-name "$TABLE" \
  --index-name gsi1 \
  --key-condition-expression "gsi1pk = :g AND gsi1sk BETWEEN :d1 AND :d2" \
  --expression-attribute-values '{
    ":g":{"S":"GENRE#afrobeat"},
    ":d1":{"S":"DATE#2024-06-01"},
    ":d2":{"S":"DATE#2024-06-30"}
  }'
```

### 3.2 One genre, only the daily KPI rows (skip top-songs items)

```bash
aws dynamodb query --table-name "$TABLE" \
  --index-name gsi1 \
  --key-condition-expression "gsi1pk = :g AND gsi1sk BETWEEN :d1 AND :d2" \
  --filter-expression "record_type = :rt" \
  --expression-attribute-values '{
    ":g":{"S":"GENRE#afrobeat"},
    ":d1":{"S":"DATE#2024-06-01"},
    ":d2":{"S":"DATE#2024-06-30"},
    ":rt":{"S":"DAILY_GENRE_KPI"}
  }'
```

### 3.3 Top N most-recent days for a genre

`--no-scan-index-forward` reads in descending sort-key order:

```bash
aws dynamodb query --table-name "$TABLE" \
  --index-name gsi1 \
  --key-condition-expression "gsi1pk = :g" \
  --no-scan-index-forward --limit 7 \
  --expression-attribute-values '{":g":{"S":"GENRE#afrobeat"}}'
```

## 4. Projection (return less data, pay less)

When you only need a few attributes:

```bash
aws dynamodb query --table-name "$TABLE" \
  --key-condition-expression "pk = :pk" \
  --projection-expression "genre, listen_count, unique_listeners" \
  --expression-attribute-values '{":pk":{"S":"DATE#2024-06-25"}}'
```

If you need a reserved word (e.g. `date`), alias it:

```bash
aws dynamodb query --table-name "$TABLE" \
  --key-condition-expression "pk = :pk" \
  --projection-expression "#d, genre, listen_count" \
  --expression-attribute-names '{"#d":"date"}' \
  --expression-attribute-values '{":pk":{"S":"DATE#2024-06-25"}}'
```

## 5. Pagination

A single Query/Scan returns at most 1 MB. Capture and re-send `LastEvaluatedKey`:

```bash
aws dynamodb query --table-name "$TABLE" \
  --key-condition-expression "pk = :pk" \
  --expression-attribute-values '{":pk":{"S":"DATE#2024-06-25"}}' \
  > page1.json

NEXT=$(jq -c '.LastEvaluatedKey // empty' page1.json)
[ -n "$NEXT" ] && aws dynamodb query --table-name "$TABLE" \
  --key-condition-expression "pk = :pk" \
  --expression-attribute-values '{":pk":{"S":"DATE#2024-06-25"}}' \
  --exclusive-start-key "$NEXT"
```

For automatic pagination, use the AWS CLI default pager or call from `boto3` with `client.get_paginator("query")`.

## 6. Scan (avoid in production)

Scans read the whole table and don't use indexes. Acceptable only for one-off diagnostics or migrations.

```bash
# Count items by record_type (still reads the whole table)
aws dynamodb scan --table-name "$TABLE" \
  --filter-expression "record_type = :rt" \
  --expression-attribute-values '{":rt":{"S":"DAILY_GENRE_KPI"}}' \
  --select COUNT
```

## 7. Python (boto3) examples

```python
import boto3
from boto3.dynamodb.conditions import Key, Attr

ddb = boto3.resource("dynamodb")
table = ddb.Table("music-streaming-dev-kpis")

# 7.1 All KPI items for a day
resp = table.query(
    KeyConditionExpression=Key("pk").eq("DATE#2024-06-25")
)

# 7.2 Top 5 genres for a day
resp = table.get_item(
    Key={"pk": "DATE#2024-06-25", "sk": "TOP_GENRES"}
)

# 7.3 Genre across a date range via GSI1
resp = table.query(
    IndexName="gsi1",
    KeyConditionExpression=(
        Key("gsi1pk").eq("GENRE#afrobeat")
        & Key("gsi1sk").between("DATE#2024-06-01", "DATE#2024-06-30")
    ),
    FilterExpression=Attr("record_type").eq("DAILY_GENRE_KPI"),
)
```

## 8. Writing a new query — checklist

Before adding a new access pattern, check:

1. Can it be answered by `pk` (Query) or `pk`+`sk` (GetItem)? If yes, use that — it's cheapest.
2. Can it be answered by `gsi1pk`? If yes, use the GSI.
3. Do you need a new access pattern that the current keys can't answer efficiently? Add a new GSI rather than scanning. Document the new pattern in section 1 of this file and update the access-pattern section of `docs/plan/music_streaming_pipeline_implementation_plan_guide.md` (section 7).
4. Reads are eventually consistent by default. If you need strong consistency, add `--consistent-read` (Query/GetItem on the base table only; not supported on GSI reads).
5. Avoid `Scan` in any code path that runs on a schedule or in response to user traffic.
