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
REGION="${REGION:-asia-southeast1}"
BQ_DATASET="${BQ_DATASET:-signals}"
GCS_BUCKET_RAW="mag-10-raw"
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
fn_name() {
  case "$1" in
    volume)     echo "mag10-volume-handler" ;;
    momentum)   echo "mag10-momentum-handler" ;;
    volatility) echo "mag10-volatility-handler" ;;
    sector)     echo "mag10-sector-handler" ;;
  esac
}

for fn in volume momentum volatility sector; do
  name="$(fn_name "${fn}")"
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
  name="$(fn_name "${fn}")"
  url=$(gcloud functions describe "${name}" \
    --gen2 \
    --project="${GCP_PROJECT_ID}" \
    --region="${REGION}" \
    --format="value(serviceConfig.uri)")
  echo "  ${fn}_function_url = \"${url}\""
done
