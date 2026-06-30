# Music Streaming Data Pipeline - End-to-End AWS Implementation Plan

Version: 2.0 (revised against real input schemas; production-hardened)
Project: Event-driven music streaming ETL pipeline with Amazon S3, EventBridge, AWS Step Functions, AWS Glue, Amazon DynamoDB, CloudWatch, and Terraform IaC.

---

## 0. What Changed From v1.0

v1.0 assumed CSV schemas that do not match the actual files in `data/`. This version is rewritten against the real schemas, completes the parts of v1.0 that were stubbed, and adds the production-grade controls needed for a real deployment. Highlights:

- Schemas, column names, and join keys now match the real `users.csv`, `songs.csv`, `streams.csv`.
- Listening-time policy made explicit: `streams.csv` has no duration column, so listen time is sourced from `songs.duration_ms / 1000` (full-play assumption). See section 5.3 for alternatives.
- DynamoDB loader now writes all three item types (daily genre KPI, top 3 songs per genre, top 5 genres).
- Validation job returns a structured result that Step Functions branches on via a `Choice` state.
- Archive / failure file movement is implemented via Lambda tasks called from Step Functions, not Pass states.
- Idempotent reprocessing: KPI job only recomputes the partition(s) touched by the trigger file, uses `partitionOverwriteMode=dynamic`, and is safe to re-run.
- CI/CD, SNS-backed alarms, EventBridge DLQ, KMS encryption, least-privilege IAM, tagging, structured logging, and unit tests added.

---

## 1. Project Goal

Build an end-to-end AWS data pipeline that processes music streaming CSV data and produces daily KPI aggregates for downstream analytics, dashboards, and applications.

Input files (real schemas, see section 5):

- `users.csv`
- `songs.csv`
- `streams.csv` (one or more per day, arriving at irregular intervals)

Core flow:

```text
CSV files -> S3 Raw Bucket -> EventBridge -> Step Functions
   -> Validate (Glue Python Shell) -> Choice
   -> Compute KPIs (Glue PySpark)
   -> Load to DynamoDB (Glue Python Shell)
   -> Archive (Lambda) -> Success
   (on any failure) -> MoveToFailed (Lambda) -> Fail
```

The pipeline must:

- Ingest CSV files from Amazon S3.
- Trigger automatically when new `streams/*.csv` files arrive.
- Validate required columns and basic data quality before processing.
- Join streams with songs (and optionally users) and compute six daily genre-level KPIs.
- Store query-ready results in DynamoDB using a single-table design.
- Archive processed files and quarantine failed files.
- Emit structured logs, metrics, and SNS alarms.
- Be provisioned with Terraform, deployed by CI/CD.

---

## 2. Reference Architecture

```text
Data Sources: users.csv, songs.csv, streams*.csv
        |
        v
Amazon S3 Raw Bucket
  incoming/users/    (dimension; uploaded once or refreshed periodically)
  incoming/songs/    (dimension; uploaded once or refreshed periodically)
  incoming/streams/  (events; triggers the pipeline)
        |
        v
S3 -> EventBridge (Object Created on incoming/streams/*.csv)
        |
        v                                          +-> SQS DLQ (failed deliveries)
AWS Step Functions Standard
        |
        +--> Glue Python Shell: validate_inputs        (returns {status, reason, stream_key, stream_date})
        +--> Choice: status == "VALID" ?
              |--no--> Lambda: move_to_failed -> Fail
              |--yes-> Glue PySpark: compute_kpis      (writes silver + gold Parquet for the trigger date)
                       -> Glue Python Shell: load_dynamodb (writes 3 item types for the trigger date)
                       -> Lambda: archive_success -> Success
        |
        +--> CloudWatch Logs (vended logs, ALL level, include_execution_data=true)

Outputs:
  S3 Processed bucket: silver/streams_enriched/dt=YYYY-MM-DD/, gold/.../dt=YYYY-MM-DD/
  S3 Archive bucket:   processed/YYYY/MM/DD/  and  failed/YYYY/MM/DD/
  DynamoDB:            music-streaming-<env>-kpis  (pk/sk single-table)
  CloudWatch:          metrics, alarms, dashboard; SNS topic for alerts
```

Reuse the existing diagram at `docs/architecture/architetecture_diagram.png`.

---

## 3. AWS Services Used

| Service | Purpose |
|---|---|
| Amazon S3 | Raw CSV, Glue scripts, processed Parquet, archive (processed/failed). |
| Amazon EventBridge | Detect S3 `Object Created` events under `incoming/streams/` and trigger Step Functions. |
| AWS Step Functions (Standard) | Orchestrate validate -> branch -> compute -> load -> archive, with retries, catches, and failure routing. |
| AWS Glue Python Shell | Lightweight validation and DynamoDB load. |
| AWS Glue PySpark | Distributed joins, transformations, KPI computation. |
| AWS Lambda | Archive movement (success and failure paths). |
| Amazon DynamoDB | Daily KPI items for fast downstream lookups (single-table design). |
| Amazon SQS | DLQ for EventBridge target failures. |
| Amazon SNS | Alarm fan-out (email/Slack/PagerDuty). |
| Amazon CloudWatch | Logs, metrics, dashboard, alarms. |
| AWS KMS | Customer-managed encryption keys for S3 and DynamoDB. |
| AWS IAM | Least-privilege roles per service. |
| Terraform | All infrastructure as code, environment-scoped. |
| GitHub Actions | CI: format, validate, test, plan. CD: plan + manual approval -> apply. |

---

## 4. KPI Requirements

Compute the following daily metrics:

| KPI | Definition |
|---|---|
| Listen Count | Count of stream events for tracks in a genre per day. |
| Unique Listeners | Distinct `user_id` who streamed tracks in a genre per day. |
| Total Listening Time | Sum of effective listen time (seconds) for a genre per day. See section 5.3 for the listen-time policy. |
| Average Listening Time per User | Total listening time divided by unique listeners (seconds). |
| Top 3 Songs per Genre per Day | Three most played tracks per genre per day. Ties broken by `track_id` ascending. |
| Top 5 Genres per Day | Five most popular genres by listen count per day. Ties broken by `genre` ascending. |

---

## 5. Real Input Schemas and Assumptions

### 5.1 `users.csv`

```csv
user_id,user_name,user_age,user_country,created_at
1,Norma Fisher,65,United States,2024-02-07
```

| Column | Type | Notes |
|---|---|---|
| `user_id` | integer (string-safe) | Join key to `streams.user_id`. |
| `user_name` | string | Optional in KPIs. |
| `user_age` | integer | Available for future demographic KPIs. |
| `user_country` | string | Available for future country KPIs. |
| `created_at` | date (`YYYY-MM-DD`) | Signup date. |

### 5.2 `songs.csv` (21 columns, Spotify-style)

```csv
id,track_id,artists,album_name,track_name,popularity,duration_ms,explicit,danceability,energy,key,loudness,mode,speechiness,acousticness,instrumentalness,liveness,valence,tempo,time_signature,track_genre
```

Columns used by the pipeline:

| Column | Type | Notes |
|---|---|---|
| `track_id` | string | Join key to `streams.track_id`. |
| `track_name` | string | Used in Top 3 Songs item. |
| `artists` | string | Carried into Top 3 Songs item for usability. |
| `track_genre` | string | Grouping key for all KPIs. |
| `duration_ms` | integer | Used to derive listen time. See 5.3. |

Other columns are ignored by the KPI job but are kept in the silver layer for future use.

### 5.3 `streams.csv` and the listening-time policy

```csv
user_id,track_id,listen_time
26213,4dBa8T7oDV9WvGr7kVS4Ez,2024-06-25 17:43:13
```

| Column | Type | Notes |
|---|---|---|
| `user_id` | integer (string-safe) | Join key to `users.user_id`. |
| `track_id` | string | Join key to `songs.track_id`. |
| `listen_time` | timestamp (`YYYY-MM-DD HH:MM:SS`, treated as UTC) | Event time; `stream_date = to_date(listen_time)` is the daily partition key. |

There is **no `stream_id` and no listening-duration column**. The pipeline therefore needs a listening-time policy:

- **Default (this plan)**: assume the song was played in full. `effective_listen_seconds = songs.duration_ms / 1000`. Simple, deterministic, idempotent.
- **Alternative A** - gap-based: per (user, day), order events by `listen_time`; use the gap to the next event, capped at `duration_ms / 1000`. Better fidelity but requires session windowing and is sensitive to file boundaries.
- **Alternative B** - constant default: assume a fixed value (e.g. 30s). Useless for genre-level analytics.

The default is what `compute_kpis.py` below implements. If you change the policy, change only the `effective_listen_seconds` expression - everything downstream stays the same.

### 5.4 Other assumptions

- `listen_time` is UTC.
- `users.csv` and `songs.csv` are dimensions; they are uploaded out-of-band and are expected to be present before any stream file arrives. The validation job fails fast if they are missing.
- The pipeline is triggered by stream files only. Multiple stream files can arrive for the same day; the pipeline is idempotent across re-runs (see section 13).
- Reprocessing is performed by re-uploading the stream file (which triggers the pipeline) or by manual `StartExecution` with a synthetic event.
- "Daily" means the date of the events in the trigger file. The job derives the date set from the trigger file, then writes / overwrites only those date partitions.

---

## 6. Target S3 Layout

```text
s3://music-streaming-<env>-raw/
  incoming/users/users.csv
  incoming/songs/songs.csv
  incoming/streams/<filename>.csv

s3://music-streaming-<env>-processed/
  silver/streams_enriched/dt=YYYY-MM-DD/
  gold/daily_genre_kpis/dt=YYYY-MM-DD/
  gold/top_songs_by_genre/dt=YYYY-MM-DD/
  gold/top_genres/dt=YYYY-MM-DD/

s3://music-streaming-<env>-archive/
  processed/YYYY/MM/DD/<original-filename>
  failed/YYYY/MM/DD/<original-filename>.error.json
  failed/YYYY/MM/DD/<original-filename>

s3://music-streaming-<env>-scripts/
  glue/validate_inputs.py
  glue/compute_kpis.py
  glue/load_dynamodb.py
  lambda/archive_success.zip
  lambda/archive_failure.zip
```

All buckets: block-public-access on, versioning on, SSE-KMS with a CMK, lifecycle rules transitioning processed/archive to IA after 30d and to Glacier after 180d. Raw bucket has EventBridge notifications enabled.

---

## 7. DynamoDB Design

Single table:

```text
music-streaming-<env>-kpis
```

Keys:

| Attribute | Type | Purpose |
|---|---|---|
| `pk` | String | Partition key. |
| `sk` | String | Sort key. |

Billing: `PAY_PER_REQUEST`. PITR on. SSE with CMK. (Deletion protection can be flipped on per-environment via a Terraform variable when a prod environment is added later.)

Optional GSI for cross-day genre queries (recommended once base flow is working):

- `gsi1pk = GENRE#<genre>`, `gsi1sk = DATE#<yyyy-mm-dd>` -> efficient "show me this genre across the last N days".

### 7.1 Daily Genre KPI item

```json
{
  "pk": "DATE#2024-06-25",
  "sk": "GENRE#afrobeat",
  "record_type": "DAILY_GENRE_KPI",
  "date": "2024-06-25",
  "genre": "afrobeat",
  "listen_count": 1532,
  "unique_listeners": 842,
  "total_listening_time_seconds": 291004,
  "avg_listening_time_per_user_seconds": 345.61,
  "gsi1pk": "GENRE#afrobeat",
  "gsi1sk": "DATE#2024-06-25",
  "updated_at": "2024-06-25T10:15:00Z"
}
```

### 7.2 Top 3 Songs per Genre item

```json
{
  "pk": "DATE#2024-06-25",
  "sk": "GENRE#afrobeat#TOP_SONGS",
  "record_type": "TOP_3_SONGS_BY_GENRE",
  "date": "2024-06-25",
  "genre": "afrobeat",
  "top_songs": [
    {"rank": 1, "track_id": "4dBa8T...", "track_name": "Song A", "artists": "Artist 1", "listen_count": 901},
    {"rank": 2, "track_id": "2LoQWx...", "track_name": "Song B", "artists": "Artist 2", "listen_count": 812},
    {"rank": 3, "track_id": "7cfG5l...", "track_name": "Song C", "artists": "Artist 3", "listen_count": 799}
  ],
  "updated_at": "2024-06-25T10:15:00Z"
}
```

### 7.3 Top 5 Genres item

```json
{
  "pk": "DATE#2024-06-25",
  "sk": "TOP_GENRES",
  "record_type": "TOP_5_GENRES",
  "date": "2024-06-25",
  "top_genres": [
    {"rank": 1, "genre": "afrobeat", "listen_count": 15320},
    {"rank": 2, "genre": "pop", "listen_count": 14100},
    {"rank": 3, "genre": "hip-hop", "listen_count": 13700},
    {"rank": 4, "genre": "r-n-b", "listen_count": 12100},
    {"rank": 5, "genre": "gospel", "listen_count": 9900}
  ],
  "updated_at": "2024-06-25T10:15:00Z"
}
```

Access patterns:

- Get all KPI items for a date: `Query pk = DATE#<d>`.
- Get one genre KPI for a date: `GetItem pk = DATE#<d>, sk = GENRE#<g>`.
- Get top songs for a (date, genre): `GetItem pk = DATE#<d>, sk = GENRE#<g>#TOP_SONGS`.
- Get top genres for a date: `GetItem pk = DATE#<d>, sk = TOP_GENRES`.
- Genre across days (via GSI1): `Query gsi1pk = GENRE#<g>, gsi1sk between DATE#<d1> and DATE#<d2>`.

Hot-partition note: `pk = DATE#…` concentrates a single day on one partition. For the KPI write pattern (small daily aggregate cardinality, on the order of hundreds of items) this is fine. Do not use this scheme for raw event ingestion.

---

## 8. Repository Structure

```text
music-streaming-pipeline/
  README.md

  .github/
    workflows/
      ci.yml
      cd.yml

  docs/
    architecture/architetecture_diagram.png
    plan/music_streaming_pipeline_implementation_plan_guide.md
    runbook.md
    dynamodb_queries.md

  infra/
    envs/
      dev/    { main.tf, variables.tf, terraform.tfvars, outputs.tf, backend.tf }
    modules/
      s3/            { main.tf, variables.tf, outputs.tf }
      kms/           { main.tf, variables.tf, outputs.tf }
      iam/           { main.tf, variables.tf, outputs.tf, policies/*.json }
      dynamodb/      { main.tf, variables.tf, outputs.tf }
      glue/          { main.tf, variables.tf, outputs.tf }
      lambda/        { main.tf, variables.tf, outputs.tf }
      step_functions/{ main.tf, variables.tf, outputs.tf }
      eventbridge/   { main.tf, variables.tf, outputs.tf }
      monitoring/    { main.tf, variables.tf, outputs.tf }

  state_machine/
    pipeline.asl.json

  glue_jobs/
    validate_inputs.py
    compute_kpis.py
    load_dynamodb.py
    common/logging_utils.py

  lambda/
    archive_success/  { handler.py, requirements.txt }
    archive_failure/  { handler.py, requirements.txt }

  sample_data/         # symlink or copy of /data
    users/users.csv
    songs/songs.csv
    streams/streams1.csv ...

  tests/
    unit/
      test_validation.py
      test_kpi_logic.py
      test_dynamodb_items.py
    fixtures/
      users_sample.csv
      songs_sample.csv
      streams_sample.csv
    conftest.py

  scripts/
    upload_sample.sh
    trigger_manual.sh
    invoke_failure_test.sh

  pyproject.toml        # ruff, black, pytest config
  Makefile              # make fmt|lint|test|plan|apply|destroy
```

---

## 9. Local Prerequisites

- AWS CLI v2, Terraform >= 1.6, Python 3.10+, Git, Docker (for Lambda packaging), an AWS account with sufficient permissions in the dev account.

```bash
aws sts get-caller-identity
terraform version
python --version
```

---

## 10. Implementation Roadmap

```text
 1. Repo scaffolding + CI skeleton + pre-commit (ruff/black/terraform fmt).
 2. KMS + S3 + tagging baseline.
 3. DynamoDB with PITR + (optional) GSI1.
 4. IAM module with least-privilege policies per role.
 5. Glue validation script + unit tests.
 6. Glue KPI script + unit tests on a local Spark session.
 7. DynamoDB loader (all 3 item types) + unit tests using moto.
 8. Glue Terraform module + upload scripts + smoke test in Glue console.
 9. Lambda archive functions + unit tests.
10. Step Functions ASL with Choice + Catch/Retry + Lambda integration.
11. EventBridge rule + SQS DLQ.
12. Monitoring: log groups, dashboard, alarms wired to SNS.
13. Deploy dev via CI.
14. End-to-end happy path on sample data.
15. Failure tests (missing column, bad timestamp, empty file, missing dimension).
16. Runbook + DynamoDB query doc + demo script.
```

---

# Part A - Build the Data Layer

---

## 11. Sample Data

The real files in `data/` are the source of truth. For unit tests use the trimmed fixtures under `tests/fixtures/` (a handful of rows that exercise multi-genre, multi-user, and edge cases like null `user_id`).

---

## 12. Glue Job 1 - Validate Inputs (Python Shell)

File: `glue_jobs/validate_inputs.py`

Responsibilities:

- Resolve the stream object key from the event.
- Confirm `incoming/users/users.csv` and `incoming/songs/songs.csv` exist.
- Validate required columns on all three files.
- Validate basic data quality on the trigger streams file: non-empty, no null join keys, parseable `listen_time`.
- Compute and return the set of `stream_date` values found in the trigger file.
- Return a structured result via S3 (so Step Functions can branch on it).

Required columns (real schemas):

```python
REQUIRED_COLUMNS = {
    "users":   ["user_id", "user_name", "user_age", "user_country", "created_at"],
    "songs":   ["track_id", "artists", "track_name", "duration_ms", "track_genre"],
    "streams": ["user_id", "track_id", "listen_time"],
}
```

Result contract (written to `s3://<scripts-bucket>/validation_results/<execution_id>.json`):

```json
{
  "status": "VALID",
  "reason": "ok",
  "raw_bucket": "music-streaming-dev-raw",
  "stream_key": "incoming/streams/streams1.csv",
  "stream_dates": ["2024-06-25"]
}
```

or

```json
{
  "status": "INVALID",
  "reason": "streams: missing required columns ['track_id']",
  "raw_bucket": "music-streaming-dev-raw",
  "stream_key": "incoming/streams/streams1.csv",
  "stream_dates": []
}
```

Skeleton:

```python
import sys, json, os, uuid, logging
import boto3
import pandas as pd
from io import BytesIO
from awsglue.utils import getResolvedOptions

log = logging.getLogger("validate_inputs")
logging.basicConfig(level=logging.INFO, format='{"level":"%(levelname)s","msg":"%(message)s"}')

REQUIRED_COLUMNS = {
    "users":   ["user_id", "user_name", "user_age", "user_country", "created_at"],
    "songs":   ["track_id", "artists", "track_name", "duration_ms", "track_genre"],
    "streams": ["user_id", "track_id", "listen_time"],
}

s3 = boto3.client("s3")

def head(bucket, key):
    try:
        s3.head_object(Bucket=bucket, Key=key)
        return True
    except s3.exceptions.ClientError:
        return False

def read_csv(bucket, key):
    obj = s3.get_object(Bucket=bucket, Key=key)
    return pd.read_csv(BytesIO(obj["Body"].read()))

def validate_columns(df, name):
    missing = [c for c in REQUIRED_COLUMNS[name] if c not in df.columns]
    if missing:
        raise ValueError(f"{name}: missing required columns {missing}")

def write_result(bucket, key, payload):
    s3.put_object(Bucket=bucket, Key=key, Body=json.dumps(payload).encode("utf-8"),
                  ContentType="application/json", ServerSideEncryption="aws:kms")

def main():
    args = getResolvedOptions(sys.argv, ["event", "scripts_bucket", "execution_id"])
    event = json.loads(args["event"])
    scripts_bucket = args["scripts_bucket"]
    execution_id = args["execution_id"]
    result_key = f"validation_results/{execution_id}.json"

    raw_bucket = event["detail"]["bucket"]["name"]
    stream_key = event["detail"]["object"]["key"]
    base = {"raw_bucket": raw_bucket, "stream_key": stream_key, "stream_dates": []}

    try:
        for path, name in [("incoming/users/users.csv", "users"),
                           ("incoming/songs/songs.csv", "songs")]:
            if not head(raw_bucket, path):
                raise FileNotFoundError(f"{name}: dimension file missing at s3://{raw_bucket}/{path}")

        users   = read_csv(raw_bucket, "incoming/users/users.csv")
        songs   = read_csv(raw_bucket, "incoming/songs/songs.csv")
        streams = read_csv(raw_bucket, stream_key)

        for df, n in [(users, "users"), (songs, "songs"), (streams, "streams")]:
            validate_columns(df, n)

        if streams.empty:
            raise ValueError("streams: file is empty")
        if streams["user_id"].isnull().any():
            raise ValueError("streams: null user_id")
        if streams["track_id"].isnull().any():
            raise ValueError("streams: null track_id")
        parsed = pd.to_datetime(streams["listen_time"], errors="coerce", utc=True)
        if parsed.isnull().any():
            raise ValueError("streams: unparseable listen_time values")

        stream_dates = sorted(parsed.dt.date.astype(str).unique().tolist())
        result = {"status": "VALID", "reason": "ok", **base, "stream_dates": stream_dates}
        log.info(json.dumps(result))
        write_result(scripts_bucket, result_key, result)

    except Exception as e:
        result = {"status": "INVALID", "reason": str(e), **base}
        log.error(json.dumps(result))
        write_result(scripts_bucket, result_key, result)
        # Do not raise; Step Functions reads the JSON and branches via Choice.

if __name__ == "__main__":
    main()
```

Why write to S3 instead of relying on job stdout: `glue:startJobRun.sync` exposes only run status/metadata to Step Functions, not the job's stdout. Writing a small JSON to a known key gives the workflow a structured branch input.

---

## 13. Glue Job 2 - Compute KPIs (PySpark)

File: `glue_jobs/compute_kpis.py`

Responsibilities:

- Read the trigger stream file, plus `users.csv` and `songs.csv`.
- Filter to the set of `stream_date`s present in the trigger file (idempotency).
- Join `streams` to `songs` on `track_id`, and to `users` on `user_id` (left join).
- Derive `effective_listen_seconds` from `songs.duration_ms` per section 5.3.
- Compute all six KPIs.
- Write Parquet outputs partitioned by `stream_date` using `partitionOverwriteMode=dynamic` so only the touched partitions are replaced.

Key code:

```python
import sys, json
from awsglue.utils import getResolvedOptions
from pyspark.sql import SparkSession, Window
from pyspark.sql.functions import (
    col, count, countDistinct, sum as spark_sum, to_date, to_timestamp,
    row_number, dense_rank, current_timestamp, collect_list, struct, lit
)

def main():
    args = getResolvedOptions(sys.argv, [
        "raw_bucket", "processed_bucket", "stream_key", "stream_dates"
    ])
    raw = args["raw_bucket"]
    processed = args["processed_bucket"]
    stream_key = args["stream_key"]
    stream_dates = json.loads(args["stream_dates"])  # ["2024-06-25", ...]

    spark = (SparkSession.builder
             .appName("music-streaming-compute-kpis")
             .config("spark.sql.sources.partitionOverwriteMode", "dynamic")
             .getOrCreate())

    users   = spark.read.option("header", True).csv(f"s3://{raw}/incoming/users/users.csv")
    songs   = spark.read.option("header", True).csv(f"s3://{raw}/incoming/songs/songs.csv")
    streams = spark.read.option("header", True).csv(f"s3://{raw}/{stream_key}")

    streams = (streams
        .withColumn("listen_ts", to_timestamp("listen_time"))
        .withColumn("stream_date", to_date("listen_ts"))
        .filter(col("stream_date").isin(stream_dates))
        .dropDuplicates(["user_id", "track_id", "listen_ts"]))  # idempotency within file

    songs = (songs.select(
        col("track_id"),
        col("track_name"),
        col("artists"),
        col("track_genre").alias("genre"),
        (col("duration_ms").cast("long") / lit(1000)).alias("effective_listen_seconds")))

    enriched = (streams
        .join(songs, on="track_id", how="inner")
        .join(users.select("user_id", "user_country"), on="user_id", how="left"))

    # 1. Daily genre KPIs
    daily_genre = (enriched
        .groupBy("stream_date", "genre")
        .agg(
            count("*").alias("listen_count"),
            countDistinct("user_id").alias("unique_listeners"),
            spark_sum("effective_listen_seconds").alias("total_listening_time_seconds"),
        )
        .withColumn("avg_listening_time_per_user_seconds",
                    col("total_listening_time_seconds") / col("unique_listeners"))
        .withColumn("updated_at", current_timestamp()))

    # 2. Top 3 songs per genre per day (dense_rank for ties, tiebreaker on track_id asc)
    song_counts = (enriched
        .groupBy("stream_date", "genre", "track_id", "track_name", "artists")
        .agg(count("*").alias("listen_count")))
    w_song = Window.partitionBy("stream_date", "genre").orderBy(
        col("listen_count").desc(), col("track_id").asc())
    top_songs = (song_counts
        .withColumn("rank", row_number().over(w_song))
        .filter(col("rank") <= 3))

    # 3. Top 5 genres per day
    w_genre = Window.partitionBy("stream_date").orderBy(
        col("listen_count").desc(), col("genre").asc())
    top_genres = (daily_genre
        .withColumn("rank", row_number().over(w_genre))
        .filter(col("rank") <= 5)
        .select("stream_date", "genre", "listen_count", "rank"))

    # Writes - only the touched partitions are overwritten
    (enriched.write.mode("overwrite").partitionBy("stream_date")
        .parquet(f"s3://{processed}/silver/streams_enriched/"))
    (daily_genre.write.mode("overwrite").partitionBy("stream_date")
        .parquet(f"s3://{processed}/gold/daily_genre_kpis/"))
    (top_songs.write.mode("overwrite").partitionBy("stream_date")
        .parquet(f"s3://{processed}/gold/top_songs_by_genre/"))
    (top_genres.write.mode("overwrite").partitionBy("stream_date")
        .parquet(f"s3://{processed}/gold/top_genres/"))

if __name__ == "__main__":
    main()
```

Notes:

- The job is parameterised by `stream_dates` from validation, so it only touches the partitions for the trigger file's dates. Re-uploading the same file produces the same partitions and the same outputs (idempotent).
- `dropDuplicates(["user_id", "track_id", "listen_ts"])` collapses exact event duplicates that re-uploads can introduce.
- `partitionOverwriteMode=dynamic` is critical: without it, `mode("overwrite")` would wipe every existing partition.

---

## 14. Glue Job 3 - Load DynamoDB (Python Shell)

File: `glue_jobs/load_dynamodb.py`

Responsibilities:

- Read the gold Parquet outputs filtered to `stream_dates`.
- Convert to the three DynamoDB item shapes defined in section 7.
- Upsert with `batch_writer`, using `overwrite_by_pkeys=["pk","sk"]` so each (pk,sk) is replaced cleanly.
- Convert floats with `Decimal` to satisfy DynamoDB's number type.

Skeleton:

```python
import sys, json, boto3
from datetime import datetime, timezone
from decimal import Decimal
import pyarrow.dataset as ds   # Python Shell can read Parquet via pyarrow
from awsglue.utils import getResolvedOptions

def dec(v):
    return None if v is None else Decimal(str(round(float(v), 4)))

def main():
    args = getResolvedOptions(sys.argv, [
        "processed_bucket", "dynamodb_table", "stream_dates"
    ])
    processed = args["processed_bucket"]
    table_name = args["dynamodb_table"]
    dates = json.loads(args["stream_dates"])

    table = boto3.resource("dynamodb").Table(table_name)
    updated_at = datetime.now(timezone.utc).isoformat()

    def read_gold(prefix):
        # Read only the partitions for the trigger dates
        paths = [f"s3://{processed}/gold/{prefix}/stream_date={d}/" for d in dates]
        return ds.dataset(paths, format="parquet").to_table().to_pylist()

    daily   = read_gold("daily_genre_kpis")
    songs   = read_gold("top_songs_by_genre")
    genres  = read_gold("top_genres")

    with table.batch_writer(overwrite_by_pkeys=["pk", "sk"]) as bw:
        # 1. Daily genre KPI
        for r in daily:
            d = str(r["stream_date"]); g = r["genre"]
            bw.put_item(Item={
                "pk": f"DATE#{d}", "sk": f"GENRE#{g}",
                "record_type": "DAILY_GENRE_KPI",
                "date": d, "genre": g,
                "listen_count": int(r["listen_count"]),
                "unique_listeners": int(r["unique_listeners"]),
                "total_listening_time_seconds": int(r["total_listening_time_seconds"]),
                "avg_listening_time_per_user_seconds": dec(r["avg_listening_time_per_user_seconds"]),
                "gsi1pk": f"GENRE#{g}", "gsi1sk": f"DATE#{d}",
                "updated_at": updated_at,
            })

        # 2. Top 3 songs per genre - group by (date, genre)
        from collections import defaultdict
        grouped = defaultdict(list)
        for r in songs:
            grouped[(str(r["stream_date"]), r["genre"])].append(r)
        for (d, g), rows in grouped.items():
            rows.sort(key=lambda r: r["rank"])
            bw.put_item(Item={
                "pk": f"DATE#{d}", "sk": f"GENRE#{g}#TOP_SONGS",
                "record_type": "TOP_3_SONGS_BY_GENRE",
                "date": d, "genre": g,
                "top_songs": [{
                    "rank": int(r["rank"]),
                    "track_id": r["track_id"],
                    "track_name": r["track_name"],
                    "artists": r["artists"],
                    "listen_count": int(r["listen_count"]),
                } for r in rows],
                "updated_at": updated_at,
            })

        # 3. Top 5 genres - group by date
        grouped_g = defaultdict(list)
        for r in genres:
            grouped_g[str(r["stream_date"])].append(r)
        for d, rows in grouped_g.items():
            rows.sort(key=lambda r: r["rank"])
            bw.put_item(Item={
                "pk": f"DATE#{d}", "sk": "TOP_GENRES",
                "record_type": "TOP_5_GENRES",
                "date": d,
                "top_genres": [{
                    "rank": int(r["rank"]),
                    "genre": r["genre"],
                    "listen_count": int(r["listen_count"]),
                } for r in rows],
                "updated_at": updated_at,
            })

if __name__ == "__main__":
    main()
```

Python Shell can read Parquet via `pyarrow` (add `pyarrow` to `--additional-python-modules`). If output volume ever grows past Python Shell's memory limits, swap this job for a PySpark write using the DynamoDB connector.

---

# Part B - Build Terraform IaC

---

## 15. Environment Layout and Backends

`infra/envs/dev/backend.tf`:

```hcl
terraform {
  backend "s3" {
    bucket         = "music-streaming-tfstate-<account-id>"
    key            = "envs/dev/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "music-streaming-tflock"
    encrypt        = true
  }
}
```

`infra/envs/dev/variables.tf` includes `aws_region`, `project_name`, `environment`, `alert_email`, `cmk_alias`.

Default tags are applied via the provider so every resource gets `Project`, `Environment`, `Owner`, `ManagedBy=terraform`, `CostCenter`:

```hcl
provider "aws" {
  region = var.aws_region
  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      Owner       = var.owner
      ManagedBy   = "terraform"
      CostCenter  = var.cost_center
    }
  }
}
```

---

## 16. Module - KMS

Create one CMK per environment, aliased `alias/<project>-<env>`, with key policy granting:

- Account root: full admin (break-glass).
- S3, DynamoDB, Glue, Lambda, Step Functions, CloudWatch Logs service principals: `kms:GenerateDataKey`, `kms:Decrypt`, `kms:Encrypt` scoped via `aws:SourceArn` conditions to the resources in this stack.

All buckets and the DynamoDB table use this CMK.

---

## 17. Module - S3

Per bucket: versioning on, BPA on, SSE-KMS with the CMK, EventBridge notifications on raw bucket only, lifecycle rules (Standard -> Standard-IA at 30d -> Glacier at 180d -> Expire at 1y for archive/failed; never expire for processed gold).

```hcl
resource "aws_s3_bucket_notification" "raw_eventbridge" {
  bucket      = aws_s3_bucket.raw.id
  eventbridge = true
}
```

---

## 18. Module - DynamoDB

```hcl
resource "aws_dynamodb_table" "kpis" {
  name         = "${var.name_prefix}-kpis"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  attribute { name = "pk"     type = "S" }
  attribute { name = "sk"     type = "S" }
  attribute { name = "gsi1pk" type = "S" }
  attribute { name = "gsi1sk" type = "S" }

  global_secondary_index {
    name            = "gsi1"
    hash_key        = "gsi1pk"
    range_key       = "gsi1sk"
    projection_type = "ALL"
  }

  server_side_encryption {
    enabled     = true
    kms_key_arn = var.kms_key_arn
  }

  point_in_time_recovery { enabled = true }
  deletion_protection_enabled = var.deletion_protection_enabled  # default false; flip true if a prod env is added
}
```

---

## 19. Module - IAM (least privilege)

One role per service. Each policy is JSON in `infra/modules/iam/policies/` and scoped to the actual resource ARNs.

Glue role gets:

- `s3:GetObject`, `s3:ListBucket` on `raw/*` and `incoming/*` prefixes.
- `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject`, `s3:ListBucket` on `processed/*` and `scripts/validation_results/*`.
- `dynamodb:PutItem`, `dynamodb:BatchWriteItem`, `dynamodb:DescribeTable` on the KPI table ARN only.
- `logs:CreateLogStream`, `logs:PutLogEvents` on the Glue log groups.
- `kms:Decrypt`, `kms:GenerateDataKey` on the CMK.

Step Functions role gets:

- `glue:StartJobRun`, `glue:GetJobRun`, `glue:GetJobRuns` on the three job ARNs (not `*`).
- `lambda:InvokeFunction` on the two archive Lambdas.
- `logs:CreateLogDelivery`, `logs:GetLogDelivery`, `logs:UpdateLogDelivery`, `logs:DeleteLogDelivery`, `logs:ListLogDeliveries`, `logs:PutResourcePolicy`, `logs:DescribeResourcePolicies`, `logs:DescribeLogGroups`.
- `s3:GetObject` on `scripts/validation_results/*` (to read validation output via SDK integration).

EventBridge role gets: `states:StartExecution` on the state machine ARN only.

Lambda archive role gets: `s3:GetObject`, `s3:CopyObject`, `s3:DeleteObject` on raw + archive; `logs:*` on its own log group.

---

## 20. Module - Glue Jobs

```hcl
resource "aws_glue_job" "validate" {
  name     = "${var.name_prefix}-validate-inputs"
  role_arn = var.glue_role_arn
  command {
    name            = "pythonshell"
    script_location = "s3://${var.scripts_bucket_name}/glue/validate_inputs.py"
    python_version  = "3.9"
  }
  max_capacity = 0.0625
  timeout      = 10
  default_arguments = {
    "--scripts_bucket"                   = var.scripts_bucket_name
    "--enable-continuous-cloudwatch-log" = "true"
    "--additional-python-modules"        = "pandas==2.2.2"
  }
}

resource "aws_glue_job" "compute_kpis" {
  name     = "${var.name_prefix}-compute-kpis"
  role_arn = var.glue_role_arn
  command {
    name            = "glueetl"
    script_location = "s3://${var.scripts_bucket_name}/glue/compute_kpis.py"
    python_version  = "3"
  }
  glue_version      = "4.0"
  number_of_workers = 2
  worker_type       = "G.1X"
  timeout           = 30
  default_arguments = {
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--enable-spark-ui"                  = "true"
    "--raw_bucket"                       = var.raw_bucket_name
    "--processed_bucket"                 = var.processed_bucket_name
  }
}

resource "aws_glue_job" "load_dynamodb" {
  name     = "${var.name_prefix}-load-dynamodb"
  role_arn = var.glue_role_arn
  command {
    name            = "pythonshell"
    script_location = "s3://${var.scripts_bucket_name}/glue/load_dynamodb.py"
    python_version  = "3.9"
  }
  max_capacity = 1.0
  timeout      = 15
  default_arguments = {
    "--processed_bucket"                 = var.processed_bucket_name
    "--dynamodb_table"                   = var.dynamodb_table_name
    "--enable-continuous-cloudwatch-log" = "true"
    "--additional-python-modules"        = "pyarrow==14.0.2"
  }
}
```

Scripts are uploaded via `aws_s3_object` with `etag = filemd5(...)` so changes redeploy.

---

## 21. Module - Lambda (archive_success, archive_failure)

`lambda/archive_success/handler.py`:

```python
import os, json, boto3, urllib.parse
from datetime import datetime, timezone

s3 = boto3.client("s3")
ARCHIVE_BUCKET = os.environ["ARCHIVE_BUCKET"]

def handler(event, _):
    src_bucket = event["raw_bucket"]
    src_key    = event["stream_key"]
    today      = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    filename   = src_key.split("/")[-1]
    dst_key    = f"processed/{today}/{filename}"

    s3.copy_object(
        Bucket=ARCHIVE_BUCKET, Key=dst_key,
        CopySource={"Bucket": src_bucket, "Key": src_key},
        ServerSideEncryption="aws:kms",
    )
    s3.delete_object(Bucket=src_bucket, Key=src_key)
    return {"archived_to": f"s3://{ARCHIVE_BUCKET}/{dst_key}"}
```

`lambda/archive_failure/handler.py` is the same but writes to `failed/YYYY/MM/DD/` and also drops an `<filename>.error.json` next to it containing the Step Functions error cause for debugging.

---

## 22. Module - Step Functions

`state_machine/pipeline.asl.json`:

```json
{
  "Comment": "Music streaming ETL pipeline",
  "StartAt": "ValidateInputFiles",
  "States": {
    "ValidateInputFiles": {
      "Type": "Task",
      "Resource": "arn:aws:states:::glue:startJobRun.sync",
      "Parameters": {
        "JobName": "${validate_job_name}",
        "Arguments": {
          "--event.$":        "States.JsonToString($)",
          "--scripts_bucket": "${scripts_bucket}",
          "--execution_id.$": "$$.Execution.Name"
        }
      },
      "ResultPath": "$.validateRun",
      "Retry": [{
        "ErrorEquals": ["Glue.ConcurrentRunsExceededException",
                        "Glue.AWSGlueException"],
        "IntervalSeconds": 30, "MaxAttempts": 3, "BackoffRate": 2.0
      }],
      "Catch": [{"ErrorEquals": ["States.ALL"], "ResultPath": "$.error",
                 "Next": "MoveToFailed"}],
      "Next": "GetValidationResult"
    },

    "GetValidationResult": {
      "Type": "Task",
      "Resource": "arn:aws:states:::aws-sdk:s3:getObject",
      "Parameters": {
        "Bucket": "${scripts_bucket}",
        "Key.$":  "States.Format('validation_results/{}.json', $$.Execution.Name)"
      },
      "ResultSelector": { "body.$": "States.StringToJson($.Body)" },
      "ResultPath": "$.validation",
      "Next": "IsValid"
    },

    "IsValid": {
      "Type": "Choice",
      "Choices": [{
        "Variable": "$.validation.body.status", "StringEquals": "VALID",
        "Next": "ComputeKPIs"
      }],
      "Default": "MoveToFailed"
    },

    "ComputeKPIs": {
      "Type": "Task",
      "Resource": "arn:aws:states:::glue:startJobRun.sync",
      "Parameters": {
        "JobName": "${compute_job_name}",
        "Arguments": {
          "--raw_bucket":       "${raw_bucket}",
          "--processed_bucket": "${processed_bucket}",
          "--stream_key.$":     "$.validation.body.stream_key",
          "--stream_dates.$":   "States.JsonToString($.validation.body.stream_dates)"
        }
      },
      "ResultPath": "$.computeRun",
      "Retry": [{
        "ErrorEquals": ["Glue.ConcurrentRunsExceededException"],
        "IntervalSeconds": 30, "MaxAttempts": 3, "BackoffRate": 2.0
      }],
      "Catch": [{"ErrorEquals": ["States.ALL"], "ResultPath": "$.error",
                 "Next": "MoveToFailed"}],
      "Next": "LoadDynamoDB"
    },

    "LoadDynamoDB": {
      "Type": "Task",
      "Resource": "arn:aws:states:::glue:startJobRun.sync",
      "Parameters": {
        "JobName": "${load_job_name}",
        "Arguments": {
          "--processed_bucket": "${processed_bucket}",
          "--dynamodb_table":   "${dynamodb_table}",
          "--stream_dates.$":   "States.JsonToString($.validation.body.stream_dates)"
        }
      },
      "ResultPath": "$.loadRun",
      "Retry": [{
        "ErrorEquals": ["Glue.ConcurrentRunsExceededException",
                        "ProvisionedThroughputExceededException"],
        "IntervalSeconds": 15, "MaxAttempts": 5, "BackoffRate": 2.0
      }],
      "Catch": [{"ErrorEquals": ["States.ALL"], "ResultPath": "$.error",
                 "Next": "MoveToFailed"}],
      "Next": "ArchiveSuccess"
    },

    "ArchiveSuccess": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "${archive_success_arn}",
        "Payload": {
          "raw_bucket.$": "$.validation.body.raw_bucket",
          "stream_key.$": "$.validation.body.stream_key"
        }
      },
      "ResultPath": "$.archiveResult",
      "Retry": [{"ErrorEquals": ["States.ALL"], "MaxAttempts": 3,
                 "IntervalSeconds": 5, "BackoffRate": 2.0}],
      "Catch": [{"ErrorEquals": ["States.ALL"], "ResultPath": "$.error",
                 "Next": "MoveToFailed"}],
      "Next": "Success"
    },

    "MoveToFailed": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "${archive_failure_arn}",
        "Payload": {
          "raw_bucket.$":  "$.detail.bucket.name",
          "stream_key.$":  "$.detail.object.key",
          "error.$":       "$"
        }
      },
      "ResultPath": "$.failureArchiveResult",
      "Next": "FailPipeline"
    },

    "Success":     { "Type": "Succeed" },
    "FailPipeline":{ "Type": "Fail", "Cause": "Music streaming pipeline failed" }
  }
}
```

Logging configuration enabled at `ALL` with `include_execution_data = true` to a dedicated `aws_cloudwatch_log_group` (default retention 30d; lengthen per-environment when a prod env is added).

---

## 23. Module - EventBridge + DLQ

```hcl
resource "aws_sqs_queue" "eb_dlq" {
  name                       = "${var.name_prefix}-eb-dlq"
  kms_master_key_id          = var.kms_key_arn
  message_retention_seconds  = 1209600
}

resource "aws_cloudwatch_event_rule" "stream_upload" {
  name        = "${var.name_prefix}-stream-upload"
  description = "Trigger on new stream CSVs"
  event_pattern = jsonencode({
    "source": ["aws.s3"],
    "detail-type": ["Object Created"],
    "detail": {
      "bucket": {"name": [var.raw_bucket_name]},
      "object": {"key": [{"prefix": "incoming/streams/"}, {"suffix": ".csv"}]}
    }
  })
}

resource "aws_cloudwatch_event_target" "to_sfn" {
  rule     = aws_cloudwatch_event_rule.stream_upload.name
  arn      = var.state_machine_arn
  role_arn = var.eventbridge_role_arn

  dead_letter_config { arn = aws_sqs_queue.eb_dlq.arn }

  retry_policy {
    maximum_event_age_in_seconds = 3600
    maximum_retry_attempts       = 4
  }
}
```

Alarm on `ApproximateNumberOfMessagesVisible > 0` for the DLQ.

---

## 24. Module - Monitoring

Resources:

- Log groups: `/aws/vendedlogs/states/<sfn-name>`, `/aws-glue/jobs/output`, `/aws-glue/jobs/error`, `/aws/lambda/<archive-success>`, `/aws/lambda/<archive-failure>`. Default retention 30d, KMS-encrypted (raise the retention variable per-environment if a prod env is added).
- SNS topic `<prefix>-alerts` with email subscription from `var.alert_email`.
- Alarms (all `alarm_actions = [aws_sns_topic.alerts.arn]`):
  - Step Functions `ExecutionsFailed >= 1` over 5m.
  - Step Functions `ExecutionsTimedOut >= 1` over 5m.
  - Glue per-job `glue.driver.aggregate.numFailedTasks` and job-level failure metric via EventBridge rule on Glue Job State Change `state == FAILED`.
  - EventBridge DLQ depth `> 0`.
  - Lambda errors `> 0` for either archive function.
- CloudWatch dashboard with: SFN execution status, Glue job duration, DynamoDB consumed write capacity, DLQ depth.

---

# Part C - Tests, CI/CD, Runbook

---

## 25. Unit Tests

`tests/unit/test_validation.py` (pandas-based):

```python
import json, boto3, pytest, pandas as pd
from io import BytesIO
from moto import mock_aws
from glue_jobs.validate_inputs import REQUIRED_COLUMNS, validate_columns

def test_validate_columns_passes():
    df = pd.DataFrame(columns=REQUIRED_COLUMNS["streams"])
    validate_columns(df, "streams")

def test_validate_columns_fails_on_missing():
    df = pd.DataFrame(columns=["user_id", "track_id"])
    with pytest.raises(ValueError, match="missing required columns"):
        validate_columns(df, "streams")
```

`tests/unit/test_kpi_logic.py` (PySpark local):

```python
import pytest
from pyspark.sql import SparkSession
from pyspark.sql.functions import to_timestamp, to_date, count, countDistinct, sum as ssum, col, lit

@pytest.fixture(scope="session")
def spark():
    return (SparkSession.builder.master("local[2]")
            .appName("test").getOrCreate())

def test_daily_genre_listen_count(spark):
    streams = spark.createDataFrame(
        [("u1","t1","2024-06-25 10:00:00"),
         ("u2","t1","2024-06-25 10:05:00"),
         ("u1","t2","2024-06-25 11:00:00")],
        ["user_id","track_id","listen_time"])
    songs = spark.createDataFrame(
        [("t1","Song A","Artist1","afrobeat",200000),
         ("t2","Song B","Artist2","afrobeat",180000)],
        ["track_id","track_name","artists","track_genre","duration_ms"])

    s = (streams.withColumn("ts", to_timestamp("listen_time"))
                .withColumn("stream_date", to_date("ts")))
    songs2 = (songs.withColumnRenamed("track_genre","genre")
                   .withColumn("effective_listen_seconds",
                               col("duration_ms").cast("long")/lit(1000)))
    enriched = s.join(songs2, on="track_id", how="inner")
    out = (enriched.groupBy("stream_date","genre")
                   .agg(count("*").alias("listen_count"),
                        countDistinct("user_id").alias("unique_listeners"),
                        ssum("effective_listen_seconds").alias("total")))
    row = out.collect()[0]
    assert row["listen_count"] == 3
    assert row["unique_listeners"] == 2
    assert row["total"] == 580.0  # 200+200+180
```

`tests/unit/test_dynamodb_items.py` uses `moto.mock_aws` to verify the loader writes the expected pk/sk shape.

---

## 26. CI/CD with GitHub Actions

`.github/workflows/ci.yml`:

```yaml
name: ci
on: [push, pull_request]
jobs:
  python:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.10" }
      - run: pip install -r requirements-dev.txt
      - run: ruff check . && black --check .
      - run: pytest -q

  terraform:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: hashicorp/setup-terraform@v3
      - run: terraform -chdir=infra/envs/dev fmt -check -recursive
      - run: terraform -chdir=infra/envs/dev init -backend=false
      - run: terraform -chdir=infra/envs/dev validate

  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: bridgecrewio/checkov-action@master
        with: { directory: infra }
```

`.github/workflows/cd.yml` on push to `main`: assume an OIDC deploy role, run `terraform plan` and quality gates (`tflint`, `checkov`), then `terraform apply` against the dev environment (gated by the GitHub `dev` Environment). If a prod environment is added later, extend the workflow with an additional manually-triggered prod path or split into a separate `cd-prod.yml`.

---

## 27. Deployment Commands

```bash
cd infra/envs/dev
terraform init
terraform fmt -recursive
terraform validate
terraform plan -out plan.tfplan
terraform apply plan.tfplan
terraform output
```

Outputs to capture:

```text
raw_bucket_name, processed_bucket_name, archive_bucket_name, scripts_bucket_name
dynamodb_table_name
state_machine_arn
alerts_topic_arn
eventbridge_dlq_url
```

---

## 28. Upload Sample Data

```bash
export RAW_BUCKET=$(terraform output -raw raw_bucket_name)

aws s3 cp data/users/users.csv     s3://$RAW_BUCKET/incoming/users/users.csv
aws s3 cp data/songs/songs.csv     s3://$RAW_BUCKET/incoming/songs/songs.csv
aws s3 cp data/streams/streams1.csv s3://$RAW_BUCKET/incoming/streams/streams_2024_06_25_part1.csv
```

The last copy triggers EventBridge -> Step Functions.

---

## 29. Manual Pipeline Test

```bash
SM_ARN=$(terraform output -raw state_machine_arn)
aws stepfunctions start-execution \
  --state-machine-arn "$SM_ARN" \
  --input "$(jq -n --arg b "$RAW_BUCKET" \
              '{detail:{bucket:{name:$b},object:{key:"incoming/streams/streams_2024_06_25_part1.csv"}}}')"
```

---

## 30. Verify Outputs

```bash
PROCESSED=$(terraform output -raw processed_bucket_name)
aws s3 ls s3://$PROCESSED/gold/daily_genre_kpis/    --recursive
aws s3 ls s3://$PROCESSED/gold/top_songs_by_genre/  --recursive
aws s3 ls s3://$PROCESSED/gold/top_genres/          --recursive

TABLE=$(terraform output -raw dynamodb_table_name)
aws dynamodb query --table-name $TABLE \
  --key-condition-expression "pk = :pk" \
  --expression-attribute-values '{":pk":{"S":"DATE#2024-06-25"}}'
```

Archive verification:

```bash
ARCHIVE=$(terraform output -raw archive_bucket_name)
aws s3 ls s3://$ARCHIVE/processed/ --recursive
# After a failure test:
aws s3 ls s3://$ARCHIVE/failed/    --recursive
```

---

# Part D - Failure Handling and Runbook

---

## 31. Failure Test Cases

| Scenario | Expected behaviour |
|---|---|
| Missing required column (`track_id` removed) | Validation writes `INVALID`, `IsValid` Choice routes to `MoveToFailed`, file lands in `archive/failed/.../*.csv` and `*.error.json`. |
| Unparseable `listen_time` value | Same as above. |
| Empty streams file | Same as above. |
| Missing `incoming/users/users.csv` | Validation raises FileNotFoundError, writes `INVALID`, failure path runs. |
| Dimension drift (extra columns in songs) | Pipeline succeeds (extras ignored). |
| EventBridge target throttled or SFN unreachable | After 4 retries the event lands in the EventBridge DLQ, DLQ-depth alarm fires. |
| Glue job throttled (`ConcurrentRunsExceeded`) | Step Functions retries with backoff; eventually fails to `MoveToFailed` if it cannot recover. |
| DynamoDB throttled | Load job retries via Step Functions retry policy. |

---

## 32. Runbook (`docs/runbook.md`) - sketch

- How to find the failing execution: SFN console -> Executions -> Filter Failed -> open the execution graph -> red node has the error in its `$.error`.
- How to find the failed input file: `archive/failed/YYYY/MM/DD/<filename>.error.json`.
- How to reprocess after a fix: drop the corrected file back into `incoming/streams/`. The pipeline is idempotent for the same `stream_date`s.
- How to rotate the CMK, rotate IAM credentials, restore DynamoDB from PITR, replay the EventBridge DLQ (`aws sqs receive-message` -> re-publish to default bus).

---

## 33. DynamoDB Query Examples (`docs/dynamodb_queries.md`)

```bash
# All KPI items for a day
aws dynamodb query --table-name music-streaming-dev-kpis \
  --key-condition-expression "pk = :pk" \
  --expression-attribute-values '{":pk":{"S":"DATE#2024-06-25"}}'

# One genre on one day
aws dynamodb get-item --table-name music-streaming-dev-kpis \
  --key '{"pk":{"S":"DATE#2024-06-25"},"sk":{"S":"GENRE#afrobeat"}}'

# Top songs for a (date, genre)
aws dynamodb get-item --table-name music-streaming-dev-kpis \
  --key '{"pk":{"S":"DATE#2024-06-25"},"sk":{"S":"GENRE#afrobeat#TOP_SONGS"}}'

# Top genres for a day
aws dynamodb get-item --table-name music-streaming-dev-kpis \
  --key '{"pk":{"S":"DATE#2024-06-25"},"sk":{"S":"TOP_GENRES"}}'

# Genre over a date range (via GSI1)
aws dynamodb query --table-name music-streaming-dev-kpis \
  --index-name gsi1 \
  --key-condition-expression "gsi1pk = :g AND gsi1sk BETWEEN :d1 AND :d2" \
  --expression-attribute-values '{
    ":g":{"S":"GENRE#afrobeat"},
    ":d1":{"S":"DATE#2024-06-01"},
    ":d2":{"S":"DATE#2024-06-30"}}'
```

---

## 34. Demo Script

```text
1. Show architecture diagram.
2. Show repo structure and CI green on main.
3. Show terraform outputs (already deployed).
4. Upload users.csv and songs.csv (already in place).
5. Upload streams1.csv -> show EventBridge event -> SFN execution graph.
6. Show validation result JSON in scripts bucket.
7. Show Parquet outputs in gold/.
8. Query DynamoDB for all three item types.
9. Upload a streams file missing track_id -> show INVALID branch -> file in archive/failed.
10. Show CloudWatch dashboard and an SNS email alert.
```

---

## 35. Definition of Done (v2)

```text
[ ] Terraform deploys end-to-end in dev with CI green.
[ ] Real schemas validated; pipeline succeeds on the supplied streams1/2/3.csv.
[ ] All three DynamoDB item types written for at least one day.
[ ] partitionOverwriteMode=dynamic verified by re-running and confirming other partitions untouched.
[ ] Idempotency verified: same file uploaded twice produces identical DynamoDB items.
[ ] Failure cases (missing column, bad timestamp, empty file, missing dimension) all route to MoveToFailed and land in archive/failed/.
[ ] Glue, SFN, Lambda all log to CloudWatch with structured JSON.
[ ] CloudWatch alarms wired to an SNS topic with a verified email subscription.
[ ] EventBridge DLQ empty under normal operation; alarm fires when seeded with a poison event.
[ ] DynamoDB PITR on; CMK rotation enabled.
[ ] IAM policies scoped to resource ARNs (no `*` on data planes).
[ ] Runbook covers reprocess, rotate, restore.
[ ] README explains deploy / run / test / clean up.
[ ] `terraform destroy` cleanly tears down dev.
```

---

## 36. Cleanup

```bash
cd infra/envs/dev
# Empty buckets first (terraform won't destroy non-empty buckets)
for b in $(terraform output -json | jq -r 'to_entries[] | select(.key|endswith("_bucket_name")) | .value.value'); do
  aws s3 rm "s3://$b" --recursive
done
terraform destroy
```

---

## 37. Build Order

| Day | Work |
|---|---|
| 1 | Repo, CI skeleton, KMS, S3, tagging. |
| 2 | DynamoDB + IAM least-privilege. |
| 3 | Validation script + unit tests. |
| 4 | KPI PySpark script + local Spark unit tests. |
| 5 | DynamoDB loader + moto tests. |
| 6 | Glue Terraform module + console smoke test. |
| 7 | Lambda archive functions + tests. |
| 8 | Step Functions ASL (with Choice + Catch + Retry). |
| 9 | EventBridge rule + SQS DLQ. |
| 10 | Monitoring: dashboard, alarms, SNS. |
| 11 | End-to-end happy path on real streams1/2/3.csv. |
| 12 | Failure tests + runbook + demo. |

---

## 38. References

- Step Functions with Terraform: https://docs.aws.amazon.com/step-functions/latest/dg/terraform-sfn.html
- Step Functions optimized Glue integration: https://docs.aws.amazon.com/step-functions/latest/dg/connect-glue.html
- Step Functions AWS SDK integrations (S3 GetObject, Lambda invoke): https://docs.aws.amazon.com/step-functions/latest/dg/supported-services-awssdk.html
- Start Step Functions from S3 via EventBridge: https://docs.aws.amazon.com/step-functions/latest/dg/tutorial-cloudwatch-events-s3.html
- EventBridge DLQs and retry policy: https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-rule-dlq.html
- Glue Python Shell jobs: https://docs.aws.amazon.com/glue/latest/dg/add-job-python.html
- Spark dynamic partition overwrite: https://spark.apache.org/docs/latest/sql-data-sources-load-save-functions.html#dynamic-partition-overwrites
- DynamoDB single-table design: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-modeling-nosql-B.html
- Terraform AWS provider: https://registry.terraform.io/providers/hashicorp/aws/latest/docs
