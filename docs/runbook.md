# Runbook — Music Streaming Pipeline

Operational reference for diagnosing and recovering from failures in the production pipeline. Use this in conjunction with the [DynamoDB query reference](dynamodb_queries.md) and [frontend/dashboard guide](frontend.md).

## 0. On-Call Quick Reference

When an alarm fires:

```bash
# 1. Set up your shell
ENV=${ENV:-dev}
cd $(git rev-parse --show-toplevel)
TF="terraform -chdir=infra/envs/$ENV"

# 2. Capture the failed execution
SM_ARN=$($TF output -raw state_machine_arn)
EXEC=$(aws stepfunctions list-executions --state-machine-arn "$SM_ARN" \
       --status-filter FAILED --max-results 1 \
       --query 'executions[0].executionArn' --output text)
echo "Failed execution: $EXEC"

# 3. Open it in the console
aws stepfunctions describe-execution --execution-arn "$EXEC"
```

The execution graph in the AWS Step Functions console is the fastest visual way in. Each red node carries the error reason in its output payload.

## 1. Alarm-to-Cause Mapping

The monitoring module creates these alarms; each routes to the `<project>-<env>-alerts` SNS topic.

| Alarm | What it means | First place to look |
|---|---|---|
| `*-sfn-failed` | A Step Functions execution failed in the last 5 minutes. | Step Functions console → failed execution → red node payload. |
| `*-sfn-timeout` | A Step Functions execution exceeded its timeout. | Same — usually the Glue PySpark `ComputeKPIs` step. |
| `*-lambda-archive-success-errors` | The success-path archive Lambda raised. | `/aws/lambda/<project>-<env>-archive-success` log group. |
| `*-lambda-archive-failure-errors` | The failure-path archive Lambda raised. | `/aws/lambda/<project>-<env>-archive-failure` log group. |
| `*-eventbridge-dlq-visible` | One or more S3-trigger events landed in the DLQ. | See §6 "EventBridge DLQ replay". |

## 2. Where Logs Live

| Component | Log group / source |
|---|---|
| Step Functions | `/aws/vendedlogs/states/<state-machine-name>` |
| Glue Python Shell jobs (validate, load) | `/aws-glue/python-jobs/output` and `/aws-glue/python-jobs/error` |
| Glue PySpark job (compute) | `/aws-glue/jobs/output` and `/aws-glue/jobs/error`. The Spark UI link is in the Glue console "Run details" page. |
| Lambdas | `/aws/lambda/<project>-<env>-archive-success` / `-archive-failure` |
| EventBridge rule invocations | CloudTrail (event source `events.amazonaws.com`); the rule itself has metrics in `AWS/Events`. |
| DynamoDB | `AWS/DynamoDB` metrics; CloudTrail data-plane events if enabled. |
| Validation job structured result | `s3://<scripts-bucket>/validation_results/<execution_name>.json` |

## 3. Common Failures and Recoveries

### 3.1 `ValidateInputFiles` Glue job failed

Symptom: SFN execution failed at step `ValidateInputFiles` with a Glue error.

Likely causes:

- `users.csv` or `songs.csv` not yet uploaded to `incoming/`.
- Glue role missing `s3:GetObject` on the raw bucket.
- KMS decrypt denied (raw bucket SSE-KMS).

Action:

```bash
# 1. Confirm both dimension files exist
RAW=$($TF output -raw raw_bucket_name)
aws s3 ls s3://$RAW/incoming/users/users.csv
aws s3 ls s3://$RAW/incoming/songs/songs.csv

# 2. If missing, upload from sample_data/
aws s3 cp sample_data/users/users.csv s3://$RAW/incoming/users/users.csv
aws s3 cp sample_data/songs/songs.csv s3://$RAW/incoming/songs/songs.csv

# 3. Re-trigger by re-uploading the stream file or use scripts/trigger_manual.sh
```

### 3.2 `IsValid` Choice routed to `MoveToFailed`

Symptom: SFN execution shows green through `GetValidationResult`, then a yellow `MoveToFailed`, then `FailPipeline`.

This means validation completed but found a problem. The result JSON tells you exactly which one.

Action:

```bash
SCRIPTS=$($TF output -raw scripts_bucket_name)
EXEC_NAME=$(basename "$EXEC")
aws s3 cp "s3://$SCRIPTS/validation_results/$EXEC_NAME.json" - | jq .
```

`reason` field will be one of:

- `streams: missing required columns [...]` → fix the source file's header and re-upload.
- `streams: file is empty` → producer issue; do not retry blindly.
- `streams: null user_id` / `null track_id` → producer issue; fix upstream.
- `streams: invalid listen_time` → bad timestamp formatting; fix and re-upload.

The original file is now at `s3://<archive>/failed/YYYY/MM/DD/<filename>` with its `<filename>.error.json` sibling.

### 3.3 `ComputeKPIs` Glue PySpark job failed

Symptom: SFN execution failed at `ComputeKPIs`.

Likely causes and fixes:

| Error message | Cause | Fix |
|---|---|---|
| `One or more objects could not be deleted` | Glue role missing `s3:DeleteObject` on the processed bucket. Spark's `mode("overwrite")` calls the S3 `DeleteObjects` API to clean up staging files. | Add `s3:DeleteObject` to `infra/modules/iam/policies/glue_policy.json` and re-apply. |
| `File not present on S3` | Leftover `_temporary/` staging directories from a previous failed run. Spark lists those partial files as input but they are missing. | Clear the processed bucket (`aws s3 rm s3://<processed> --recursive`) and re-trigger. The root cause — `partitionOverwriteMode=dynamic` deleting source partition files while tasks are still reading them — is guarded by `existing.cache(); existing.count()` in `compute_kpis.py`. |
| Spark OOM | Worker count too low for the input size. Default is 2 × G.1X. | Temporarily scale up (see below). |
| Schema drift | `songs.csv` column changed format (e.g. `duration_ms` with thousands separators). | Fix upstream file; null-safe coalesce in the job handles `duration_ms = null` cleanly. |

```bash
# Open the failed Glue run
JOB=$($TF output -raw glue_compute_job_name)
RUN=$(aws glue get-job-runs --job-name "$JOB" --max-results 1 \
      --query 'JobRuns[0].Id' --output text)

# Tail the driver log
aws logs tail /aws-glue/jobs/output --follow \
  --log-stream-name-prefix "$RUN"
```

To re-process after a fix: re-upload the source stream file (idempotent — same date partitions get rewritten via `partitionOverwriteMode=dynamic`).

To temporarily scale up:

```bash
aws glue update-job --job-name "$JOB" \
  --job-update '{"NumberOfWorkers": 4, "WorkerType": "G.1X"}'
```

Revert via Terraform after the incident so config stays in code.

### 3.4 `LoadDynamoDB` failed

Symptom: SFN execution failed at `LoadDynamoDB`.

Likely causes:

| Error message | Cause | Fix |
|---|---|---|
| `AccessDeniedException: dynamodb:BatchWriteItem` | Glue role missing DynamoDB permissions. | Add `dynamodb:BatchWriteItem`, `dynamodb:PutItem`, `dynamodb:UpdateItem` to `infra/modules/iam/policies/glue_policy.json` and re-apply. |
| DynamoDB throttling | Table briefly saturated; retry policy exhausted. | Re-trigger the execution — the step is idempotent. |
| `pyarrow` import error | `pyarrow` not installed in the Python Shell environment. | Add `pyarrow` to `additional-python-modules` in the Glue job Terraform config. |
| `TypeError: float() argument ... NoneType` | Null values in Parquet (e.g. `duration_ms` blank in songs). | Null-safe `or 0.0` guards are already in `load_dynamodb.py`. If you see this, the Parquet was written with an older version of the job — re-run `ComputeKPIs` first. |

```bash
JOB=$($TF output -raw glue_load_job_name)
aws glue get-job-run --job-name "$JOB" \
  --run-id "$(aws glue get-job-runs --job-name "$JOB" --max-results 1 \
              --query 'JobRuns[0].Id' --output text)"

# Re-run just this stage by restarting the SFN execution with the same input
aws stepfunctions start-execution --state-machine-arn "$SM_ARN" \
  --input "$(aws stepfunctions describe-execution --execution-arn "$EXEC" \
             --query 'input' --output text)"
```

### 3.5 `ArchiveSuccess` / `MoveToFailed` Lambda failed

Symptom: SFN execution shows the compute/load steps green but archive red.

Likely causes:

- Lambda role missing `s3:CopyObject` or `s3:DeleteObject` on raw/archive buckets.
- KMS denied between the two buckets.
- Source file already moved (idempotent retry — usually safe to ignore).

Action: the source file is still in `incoming/streams/`. Manually move it:

```bash
ARCH=$($TF output -raw archive_bucket_name)
TODAY=$(date -u +%Y/%m/%d)
KEY=incoming/streams/<filename>

aws s3 mv s3://$RAW/$KEY s3://$ARCH/processed/$TODAY/$(basename $KEY)
```

## 4. Reprocessing a Date

To recompute one or more days (after a code fix, schema change, or accidental data drop):

1. Recover the original stream files from `archive/processed/YYYY/MM/DD/` (or your upstream system).
2. Re-upload them to `incoming/streams/`. The pipeline runs again; KPI Parquet partitions for those dates are overwritten in place (thanks to `partitionOverwriteMode=dynamic`), and DynamoDB items are upserted (same `pk`/`sk`).

```bash
# Example: replay everything that ran on 2024-06-25
aws s3 ls s3://$ARCH/processed/2024/06/25/ \
  | awk '{print $4}' \
  | while read f; do
      aws s3 cp "s3://$ARCH/processed/2024/06/25/$f" "s3://$RAW/incoming/streams/$f"
    done
```

Alternatively start one execution manually with a synthetic event:

```bash
aws stepfunctions start-execution --state-machine-arn "$SM_ARN" \
  --input "$(jq -n --arg b "$RAW" --arg k "incoming/streams/streams1.csv" \
             '{detail:{bucket:{name:$b},object:{key:$k}}}')"
```

## 5. DynamoDB Restore from PITR

Point-in-time recovery is enabled on the KPI table.

```bash
TABLE=$($TF output -raw dynamodb_table_name)

# Restore to a sibling table
aws dynamodb restore-table-to-point-in-time \
  --source-table-name "$TABLE" \
  --target-table-name "${TABLE}-restore-$(date -u +%Y%m%dT%H%M%S)" \
  --restore-date-time "$(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%SZ)"
```

After verification, swap by renaming or rebuilding pointers in the consuming applications. The original table is not modified by the restore.

## 6. EventBridge DLQ Replay

When `*-eventbridge-dlq-visible` fires:

```bash
DLQ=$($TF output -raw eventbridge_dlq_url)

# Inspect a couple of messages without deleting them
aws sqs receive-message --queue-url "$DLQ" --max-number-of-messages 5 \
  --visibility-timeout 30 --message-attribute-names All --attribute-names All
```

Each message body is the original S3 event that failed to deliver. After fixing the underlying issue (usually IAM permissions or a misconfigured rule), replay by re-publishing the events to the default bus, or simpler: re-upload the affected stream files so a fresh `Object Created` event is generated.

To drain the DLQ once you're confident the events are recoverable elsewhere:

```bash
aws sqs purge-queue --queue-url "$DLQ"
```

## 7. KMS Key Rotation

The CMK has automatic annual rotation on by default. To rotate manually outside the cycle, or to add a new key:

1. Create a new key in `infra/modules/kms/main.tf` (e.g. `aws_kms_key.rotation_v2`).
2. Update all consumers to reference the new key.
3. Apply; AWS encrypts new writes with the new key. Old data is re-encrypted on next write.
4. Schedule the old key for deletion (`aws kms schedule-key-deletion`) only after confirming no resource still references it (search by ARN in CloudTrail).

## 8. Glue Concurrency Limits

The Glue jobs are configured for `MaxConcurrentRuns = 1` by default. If a burst of stream files arrives:

- The Step Functions `Glue.ConcurrentRunsExceededException` retry policy (3 attempts, exponential backoff) handles small bursts.
- For sustained bursts, increase `--MaxConcurrentRuns` on the relevant job (via Terraform) or introduce SQS-based buffering in front of EventBridge.

## 9. Cost Spike Investigation

If the monthly AWS bill jumps:

```bash
# Check DynamoDB consumed write capacity over the last 24h
aws cloudwatch get-metric-statistics \
  --namespace AWS/DynamoDB --metric-name ConsumedWriteCapacityUnits \
  --dimensions Name=TableName,Value="$TABLE" \
  --start-time "$(date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%SZ)" \
  --end-time   "$(date -u                  +%Y-%m-%dT%H:%M:%SZ)" \
  --period 3600 --statistics Sum

# Check Glue job duration sum (DPU-hours = duration * worker_count)
JOB=$($TF output -raw glue_compute_job_name)
aws glue get-job-runs --job-name "$JOB" --max-results 50 \
  --query 'JobRuns[?StartedOn>=`'$(date -u -d '7 days ago' +%Y-%m-%d)'`].[JobRunState,ExecutionTime]' \
  --output table
```

Typical causes: re-running everything by mistake (loop in re-upload script), schema drift forcing wide shuffles, or `partitionOverwriteMode` not actually `dynamic` (silently rewrites every partition).

## 10. Useful CloudTrail Queries

To find who triggered a manual execution:

```bash
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=StartExecution \
  --max-results 5
```

To find a delete on the raw bucket:

```bash
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=ResourceName,AttributeValue="$RAW" \
  --max-results 20 \
  --query 'Events[?EventName==`DeleteObject`]'
```

## 11. KPI Dashboard / API Issues

| Symptom | Cause | Fix |
|---|---|---|
| "Dashboard API URL is not configured" | `config.js` not uploaded or `window.DASHBOARD_CONFIG` missing | Re-run `make apply`; verify `aws_s3_object.config` in the dashboard bucket |
| "No KPI dates found yet" | Pipeline hasn't run successfully; DynamoDB empty | Run the pipeline and verify DynamoDB items exist |
| Dashboard 403 on load | S3 bucket policy not applied | Re-run `make apply`; check public-read bucket policy in S3 console |
| API 500 from Lambda | Missing `DYNAMODB_TABLE` env var or missing `dynamodb:Query`/`GetItem`/`Scan` | Check Lambda env vars in console; verify `lambda_policy.json` |
| Lambda missing `dynamodb:Query` | Lambda role policy doesn't include read operations | Add `dynamodb:Query`, `dynamodb:GetItem`, `dynamodb:Scan` to `infra/modules/iam/policies/lambda_policy.json` |

For full details see [`docs/frontend.md`](frontend.md).

## 12. Escalation

| Severity | Definition | Action |
|---|---|---|
| SEV-1 | DynamoDB KPI table unavailable; downstream reports broken. | Page on-call. Restore from PITR (§5). |
| SEV-2 | Pipeline failing for > 1 hour; daily KPIs delayed. | Triage with §1–§3. Notify stakeholders. |
| SEV-3 | Single execution failed; subsequent runs succeed. | Investigate during business hours; root-cause via §3. |
| SEV-4 | Alarm flapping; no data impact. | Adjust thresholds in `infra/modules/monitoring/`. |

## 13. Post-Incident

After resolving:

1. Add (or update) the failure scenario in §3 of this file.
2. If a code change was needed, link the PR.
3. If a Terraform change was needed, ensure it was applied via CI/CD, not by hand.
4. Schedule a 15-minute review with the team if the incident exceeded SEV-3.
