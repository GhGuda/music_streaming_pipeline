#!/usr/bin/env bash
# trigger_manual.sh — start a Step Functions execution against an existing S3 key
#
# Use this for reprocessing without re-uploading the file. The state machine
# expects an S3 "Object Created" shaped event in its input.
#
# Usage:
#   scripts/trigger_manual.sh <stream_key>
#   scripts/trigger_manual.sh incoming/streams/streams1.csv
#
# Environment overrides:
#   ENV       - Terraform env (default: dev)
#   PROFILE   - AWS CLI profile (optional)
#   WAIT      - "1" to poll the execution until it terminates (default: 0)

set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <stream_key>" >&2
  echo "Example: $0 incoming/streams/streams1.csv" >&2
  exit 2
fi

STREAM_KEY="$1"
ENV="${ENV:-dev}"
TF_DIR="infra/envs/${ENV}"

PROFILE_FLAG=()
[[ -n "${PROFILE:-}" ]] && PROFILE_FLAG=(--profile "$PROFILE")

RAW_BUCKET="$(terraform -chdir="$TF_DIR" output -raw raw_bucket_name)"
SM_ARN="$(terraform     -chdir="$TF_DIR" output -raw state_machine_arn)"

# Verify the object exists before triggering — fail fast if not
if ! aws "${PROFILE_FLAG[@]}" s3api head-object \
      --bucket "$RAW_BUCKET" --key "$STREAM_KEY" >/dev/null 2>&1; then
  echo "Object not found: s3://$RAW_BUCKET/$STREAM_KEY" >&2; exit 1
fi

INPUT="$(jq -n --arg b "$RAW_BUCKET" --arg k "$STREAM_KEY" \
           '{detail:{bucket:{name:$b},object:{key:$k}}}')"

NAME="manual-$(date -u +%Y%m%dT%H%M%SZ)-$RANDOM"

echo "Starting execution $NAME"
echo "  state-machine: $SM_ARN"
echo "  input.detail.object.key: $STREAM_KEY"

EXEC_ARN="$(aws "${PROFILE_FLAG[@]}" stepfunctions start-execution \
              --state-machine-arn "$SM_ARN" \
              --name "$NAME" \
              --input "$INPUT" \
              --query executionArn --output text)"

echo "Execution ARN: $EXEC_ARN"

if [[ "${WAIT:-0}" == "1" ]]; then
  echo "Waiting for execution to terminate..."
  while :; do
    STATUS="$(aws "${PROFILE_FLAG[@]}" stepfunctions describe-execution \
                --execution-arn "$EXEC_ARN" --query status --output text)"
    case "$STATUS" in
      SUCCEEDED) echo "SUCCEEDED"; exit 0 ;;
      FAILED|TIMED_OUT|ABORTED)
        echo "$STATUS"
        aws "${PROFILE_FLAG[@]}" stepfunctions describe-execution \
          --execution-arn "$EXEC_ARN" \
          --query '{cause:cause,error:error,output:output}'
        exit 1 ;;
      *) sleep 5 ;;
    esac
  done
fi
