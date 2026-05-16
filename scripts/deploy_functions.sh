#!/usr/bin/env bash
# Deploy the archive and gcs-to-bq Cloud Functions (Gen 2) to GCP.
#
# Usage:
#   export GCP_PROJECT_ID=your-project-id
#   export REGION=asia-southeast1   # optional
#   export BQ_DATASET=signals        # optional
#   ./scripts/deploy_functions.sh
#
# Two-phase deployment:
#   Phase 1: run this script — it prints the archive function URL.
#   Phase 2: add archive_function_url to infra/terraform.tfvars, then run
#            terraform apply to switch the Pub/Sub subscription to push mode.

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
for fn in archive gcs_to_bq; do
  cp -r "${FUNCTIONS_DIR}/shared" "${FUNCTIONS_DIR}/${fn}/shared"
done

cleanup() {
  for fn in archive gcs_to_bq; do
    rm -rf "${FUNCTIONS_DIR}/${fn}/shared"
  done
}
trap cleanup EXIT

# ---------------------------------------------------------------------------
# Deploy: archive (HTTP trigger — receives Pub/Sub push payloads)
# ---------------------------------------------------------------------------
echo "Deploying mag10-archive ..."
gcloud functions deploy mag10-archive \
  --gen2 \
  --project="${GCP_PROJECT_ID}" \
  --region="${REGION}" \
  --runtime=python312 \
  --source="${FUNCTIONS_DIR}/archive" \
  --entry-point=handle \
  --trigger-http \
  --no-allow-unauthenticated \
  --service-account="${SA_EMAIL}" \
  --memory=256Mi \
  --timeout=60s \
  --set-env-vars="GCS_BUCKET_RAW=${GCS_BUCKET_RAW}"
echo "  Done: mag10-archive"

# ---------------------------------------------------------------------------
# Deploy: gcs-to-bq (Eventarc trigger — GCS object finalization on silver/)
# ---------------------------------------------------------------------------
echo "Deploying mag10-gcs-to-bq ..."
gcloud functions deploy mag10-gcs-to-bq \
  --gen2 \
  --project="${GCP_PROJECT_ID}" \
  --region="${REGION}" \
  --runtime=python312 \
  --source="${FUNCTIONS_DIR}/gcs_to_bq" \
  --entry-point=handle \
  --trigger-event-filters="type=google.cloud.storage.object.v1.finalized" \
  --trigger-event-filters="bucket=${GCS_BUCKET_RAW}" \
  --trigger-location="${REGION}" \
  --service-account="${SA_EMAIL}" \
  --memory=256Mi \
  --timeout=120s \
  --set-env-vars="GCP_PROJECT_ID=${GCP_PROJECT_ID},BQ_DATASET=${BQ_DATASET}"
echo "  Done: mag10-gcs-to-bq"

# ---------------------------------------------------------------------------
# Print archive URL for terraform.tfvars
# ---------------------------------------------------------------------------
ARCHIVE_URL=$(gcloud functions describe mag10-archive \
  --gen2 \
  --project="${GCP_PROJECT_ID}" \
  --region="${REGION}" \
  --format="value(serviceConfig.uri)")

echo ""
echo "Add to infra/terraform.tfvars, then run terraform apply:"
echo ""
echo "  archive_function_url = \"${ARCHIVE_URL}\""
