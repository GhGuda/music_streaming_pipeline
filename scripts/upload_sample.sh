#!/usr/bin/env bash
# upload_sample.sh — upload dimension + stream CSVs to the raw bucket
#
# Usage:
#   scripts/upload_sample.sh [stream_file ...]
#
# With no arguments, uploads users.csv, songs.csv, and every sample_data/streams/streams*.csv.
# With arguments, uploads users.csv + songs.csv once, then the given stream files
# (each as a uniquely-named object so each triggers a Step Functions execution).
#
# Environment overrides:
#   ENV         - Terraform env (default: dev)
#   DATA_DIR    - Where the CSVs live (default: sample_data)
#   PROFILE     - AWS CLI profile (optional)

set -euo pipefail

ENV="${ENV:-dev}"
DATA_DIR="${DATA_DIR:-sample_data}"
TF_DIR="infra/envs/${ENV}"

if ! command -v terraform >/dev/null; then
  echo "terraform not found in PATH" >&2; exit 1
fi
if ! command -v aws >/dev/null; then
  echo "aws CLI not found in PATH" >&2; exit 1
fi

PROFILE_FLAG=()
[[ -n "${PROFILE:-}" ]] && PROFILE_FLAG=(--profile "$PROFILE")

RAW_BUCKET="$(terraform -chdir="$TF_DIR" output -raw raw_bucket_name)"
echo "Raw bucket: s3://$RAW_BUCKET"

upload() {
  local src="$1" dst="$2"
  [[ -f "$src" ]] || { echo "  skip (missing): $src"; return 0; }
  echo "  -> s3://$RAW_BUCKET/$dst"
  aws "${PROFILE_FLAG[@]}" s3 cp "$src" "s3://$RAW_BUCKET/$dst"
}

# 1. Dimensions
echo "Uploading dimensions..."
upload "$DATA_DIR/users/users.csv" "incoming/users/users.csv"
upload "$DATA_DIR/songs/songs.csv" "incoming/songs/songs.csv"

# 2. Streams
echo "Uploading streams..."
if [[ $# -gt 0 ]]; then
  STREAMS=("$@")
else
  mapfile -t STREAMS < <(ls "$DATA_DIR"/streams/streams*.csv 2>/dev/null || true)
fi

if [[ ${#STREAMS[@]} -eq 0 ]]; then
  echo "  no stream files found under $DATA_DIR/streams/" >&2; exit 1
fi

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
for f in "${STREAMS[@]}"; do
  base="$(basename "$f")"
  # Make the destination key unique so a re-upload still triggers EventBridge
  # but stays human-readable (e.g. streams1_20240625T101512Z.csv).
  name="${base%.csv}_${STAMP}.csv"
  upload "$f" "incoming/streams/$name"
done

echo "Done. Each stream upload should trigger one Step Functions execution."
echo "Watch executions:"
echo "  aws stepfunctions list-executions --state-machine-arn \\"
echo "    \$(terraform -chdir=$TF_DIR output -raw state_machine_arn) --max-results 5"
