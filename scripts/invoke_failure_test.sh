#!/usr/bin/env bash
# invoke_failure_test.sh — synthesize bad stream files and confirm the pipeline
# rejects them. Each scenario should end with the file in s3://<archive>/failed/
# and the execution status FAILED.
#
# Usage:
#   scripts/invoke_failure_test.sh [scenario ...]
#
# Scenarios:
#   missing-column       Streams CSV without the track_id column.
#   bad-timestamp        Streams CSV with an unparseable listen_time.
#   empty-file           Zero-byte streams CSV.
#   missing-dimension    Removes users.csv before triggering (DESTRUCTIVE; restored at end).
#
# Default: runs missing-column, bad-timestamp, empty-file (non-destructive).
#
# Environment overrides:
#   ENV       - Terraform env (default: dev)
#   PROFILE   - AWS CLI profile (optional)
#   DATA_DIR  - source of users.csv/songs.csv when restoring (default: sample_data)

set -euo pipefail

ENV="${ENV:-dev}"
TF_DIR="infra/envs/${ENV}"
DATA_DIR="${DATA_DIR:-sample_data}"

PROFILE_FLAG=()
[[ -n "${PROFILE:-}" ]] && PROFILE_FLAG=(--profile "$PROFILE")

RAW_BUCKET="$(terraform -chdir="$TF_DIR" output -raw raw_bucket_name)"
ARCHIVE_BUCKET="$(terraform -chdir="$TF_DIR" output -raw archive_bucket_name)"
SM_ARN="$(terraform     -chdir="$TF_DIR" output -raw state_machine_arn)"

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

upload_and_check() {
  local local_file="$1" label="$2"
  local stamp; stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  local key="incoming/streams/${label}_${stamp}.csv"

  echo
  echo "===== scenario: $label ====="
  echo "Uploading $local_file -> s3://$RAW_BUCKET/$key"
  aws "${PROFILE_FLAG[@]}" s3 cp "$local_file" "s3://$RAW_BUCKET/$key"

  # Give EventBridge a moment to fire and SFN to create the execution.
  echo "Waiting for execution to register..."
  sleep 8

  # Find the execution whose name embeds this key (or simply the most recent one).
  local exec_arn
  exec_arn="$(aws "${PROFILE_FLAG[@]}" stepfunctions list-executions \
                --state-machine-arn "$SM_ARN" --max-results 1 \
                --query 'executions[0].executionArn' --output text)"
  echo "Tracking execution: $exec_arn"

  # Poll until it terminates.
  local status
  while :; do
    status="$(aws "${PROFILE_FLAG[@]}" stepfunctions describe-execution \
                --execution-arn "$exec_arn" --query status --output text)"
    [[ "$status" =~ ^(SUCCEEDED|FAILED|TIMED_OUT|ABORTED)$ ]] && break
    sleep 5
  done
  echo "Status: $status"

  if [[ "$status" != "FAILED" ]]; then
    echo "  EXPECTED: FAILED. Got: $status" >&2
    return 1
  fi

  # Confirm the file was moved to archive/failed/.
  local base; base="$(basename "$key")"
  echo "Looking for $base under s3://$ARCHIVE_BUCKET/failed/ ..."
  if aws "${PROFILE_FLAG[@]}" s3 ls "s3://$ARCHIVE_BUCKET/failed/" --recursive \
       | grep -q "$base"; then
    echo "  PASS: file moved to archive/failed/"
  else
    echo "  WARN: file not found under archive/failed/ (yet?)" >&2
  fi
}

scenario_missing_column() {
  # Drop track_id header + column from a real streams file
  local src="$DATA_DIR/streams/streams1.csv"
  local out="$WORKDIR/missing_column.csv"
  awk -F, 'NR==1 {print "user_id,listen_time"; next} {print $1","$3}' "$src" > "$out"
  upload_and_check "$out" "missing-column"
}

scenario_bad_timestamp() {
  local src="$DATA_DIR/streams/streams1.csv"
  local out="$WORKDIR/bad_timestamp.csv"
  # Keep the header, corrupt the timestamp on the first 3 data rows
  awk -F, 'NR==1 {print; next}
           NR<=4 {print $1","$2",not-a-date"; next}
           {print}' "$src" > "$out"
  upload_and_check "$out" "bad-timestamp"
}

scenario_empty_file() {
  local out="$WORKDIR/empty.csv"
  : > "$out"
  upload_and_check "$out" "empty-file"
}

scenario_missing_dimension() {
  # Destructive: removes incoming/users/users.csv, runs once, then restores.
  echo "Removing s3://$RAW_BUCKET/incoming/users/users.csv (will restore)"
  aws "${PROFILE_FLAG[@]}" s3 rm "s3://$RAW_BUCKET/incoming/users/users.csv" || true

  local src="$DATA_DIR/streams/streams1.csv"
  upload_and_check "$src" "missing-dimension"

  echo "Restoring users.csv"
  aws "${PROFILE_FLAG[@]}" s3 cp "$DATA_DIR/users/users.csv" \
    "s3://$RAW_BUCKET/incoming/users/users.csv"
}

scenarios=("$@")
[[ ${#scenarios[@]} -eq 0 ]] && scenarios=(missing-column bad-timestamp empty-file)

for s in "${scenarios[@]}"; do
  case "$s" in
    missing-column)    scenario_missing_column ;;
    bad-timestamp)     scenario_bad_timestamp ;;
    empty-file)        scenario_empty_file ;;
    missing-dimension) scenario_missing_dimension ;;
    *) echo "Unknown scenario: $s" >&2; exit 2 ;;
  esac
done

echo
echo "All requested scenarios completed."
