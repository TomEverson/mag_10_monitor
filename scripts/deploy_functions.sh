#!/usr/bin/env bash
# Deploy all four Cloud Functions (Gen 2) to GCP.
#
# Usage:
#   export GCP_PROJECT_ID=your-project-id
#   export REGION=us-central1          # optional, defaults below
#   export BQ_DATASET=signals           # optional, defaults below
#   ./scripts/deploy_functions.sh
#
# After this script completes it prints the four function URLs.
# Paste them into infra/terraform.tfvars and run `terraform apply`
# to switch Pub/Sub subscriptions from pull to push.

set -euo pipefail

: "${GCP_PROJECT_ID:?GCP_PROJECT_ID must be set}"
REGION="${REGION:-us-central1}"
BQ_DATASET="${BQ_DATASET:-signals}"
GCS_BUCKET_RAW="mag10-raw-${GCP_PROJECT_ID}"
SA_EMAIL="mag10-functions-sa@${GCP_PROJECT_ID}.iam.gserviceaccount.com"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FUNCTIONS_DIR="${REPO_ROOT}/functions"

# ---------------------------------------------------------------------------
# Copy shared/ into each function directory before deploying.
# GCP reads the source directory as-is; shared/ must be present alongside main.py.
# ---------------------------------------------------------------------------
for fn in volume momentum volatility sector; do
  cp -r "${FUNCTIONS_DIR}/shared" "${FUNCTIONS_DIR}/${fn}/shared"
done

cleanup() {
  for fn in volume momentum volatility sector; do
    rm -rf "${FUNCTIONS_DIR}/${fn}/shared"
  done
}
trap cleanup EXIT

# ---------------------------------------------------------------------------
# Deploy each function
# ---------------------------------------------------------------------------
declare -A FUNCTION_NAMES=(
  [volume]="mag10-volume-handler"
  [momentum]="mag10-momentum-handler"
  [volatility]="mag10-volatility-handler"
  [sector]="mag10-sector-handler"
)

for fn in volume momentum volatility sector; do
  name="${FUNCTION_NAMES[$fn]}"
  echo "Deploying ${name} ..."
  gcloud functions deploy "${name}" \
    --gen2 \
    --project="${GCP_PROJECT_ID}" \
    --region="${REGION}" \
    --runtime=python312 \
    --source="${FUNCTIONS_DIR}/${fn}" \
    --entry-point=handle \
    --trigger-http \
    --no-allow-unauthenticated \
    --service-account="${SA_EMAIL}" \
    --memory=256Mi \
    --timeout=60s \
    --set-env-vars="GCP_PROJECT_ID=${GCP_PROJECT_ID},BQ_DATASET=${BQ_DATASET},GCS_BUCKET_RAW=${GCS_BUCKET_RAW}"
  echo "  Done: ${name}"
done

# ---------------------------------------------------------------------------
# Print URLs for terraform.tfvars
# ---------------------------------------------------------------------------
echo ""
echo "Function URLs — add these to infra/terraform.tfvars, then run terraform apply:"
echo ""
for fn in volume momentum volatility sector; do
  name="${FUNCTION_NAMES[$fn]}"
  url=$(gcloud functions describe "${name}" \
    --gen2 \
    --project="${GCP_PROJECT_ID}" \
    --region="${REGION}" \
    --format="value(serviceConfig.uri)")
  echo "  ${fn}_function_url = \"${url}\""
done
