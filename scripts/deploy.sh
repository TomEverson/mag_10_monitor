#!/usr/bin/env bash
# Full deployment script for mag10-monitor.
#
# Usage:
#   export GCP_PROJECT_ID=your-project-id
#   ./scripts/deploy.sh [--skip-images] [--skip-tf]
#
# Flags:
#   --skip-images   Skip Cloud Build (use when images haven't changed)
#   --skip-tf       Skip Terraform apply (use when infra hasn't changed)

set -euo pipefail

: "${GCP_PROJECT_ID:?GCP_PROJECT_ID must be set}"

REGION="${REGION:-asia-southeast1}"
ZONE="${ZONE:-asia-southeast1-b}"
BQ_DATASET="${BQ_DATASET:-signals}"
REPO="${REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/mag10-images"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
INFRA_DIR="${REPO_ROOT}/infra"
FUNCTIONS_DIR="${REPO_ROOT}/functions"

SKIP_IMAGES=false
SKIP_TF=false

for arg in "$@"; do
  case "$arg" in
    --skip-images) SKIP_IMAGES=true ;;
    --skip-tf)     SKIP_TF=true ;;
  esac
done

# ── Colours ───────────────────────────────────────────────────────────────────
BOLD='\033[1m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
RESET='\033[0m'

header()  { echo -e "\n${BOLD}${CYAN}▶ $*${RESET}"; }
ok()      { echo -e "${GREEN}✓ $*${RESET}"; }
info()    { echo -e "${YELLOW}  $*${RESET}"; }
die()     { echo -e "${RED}✗ $*${RESET}" >&2; exit 1; }

# ── Phase 1: Build images ─────────────────────────────────────────────────────
if [[ "$SKIP_IMAGES" == "true" ]]; then
  info "Skipping image builds (--skip-images)"
else
  header "Phase 1 — Building Docker images via Cloud Build"

  build_image() {
    local service=$1
    local dir="${REPO_ROOT}/${service}"
    info "Submitting ${service} build..."
    gcloud builds submit \
      --project="${GCP_PROJECT_ID}" \
      --region="${REGION}" \
      --tag="${REPO}/${service}:latest" \
      "${dir}" \
      --quiet
    ok "${service} image pushed"
  }

  # Build websocket and detection in parallel; dashboard independently
  build_image websocket &
  PID_WS=$!
  build_image detection &
  PID_DET=$!
  build_image dashboard &
  PID_DASH=$!

  wait $PID_WS   || die "websocket build failed"
  wait $PID_DET  || die "detection build failed"
  wait $PID_DASH || die "dashboard build failed"

  ok "All images built and pushed"
fi

# ── Phase 2: Terraform apply (phase 1 — infra + VMs) ─────────────────────────
if [[ "$SKIP_TF" == "true" ]]; then
  info "Skipping Terraform (--skip-tf)"
else
  header "Phase 2 — Terraform: provisioning infrastructure"

  cd "${INFRA_DIR}"

  # Write tfvars if they don't already have image values
  if [[ ! -f terraform.tfvars ]]; then
    cat > terraform.tfvars <<EOF
gcp_project_id  = "${GCP_PROJECT_ID}"
region          = "${REGION}"
zone            = "${ZONE}"
websocket_image = "${REPO}/websocket:latest"
detection_image = "${REPO}/detection:latest"
dashboard_image = "${REPO}/dashboard:latest"
EOF
    info "Created terraform.tfvars"
  fi

  terraform init -upgrade -input=false
  terraform apply -auto-approve -input=false

  ok "Terraform phase 1 complete"
  cd "${REPO_ROOT}"
fi

# ── Phase 3: Deploy Cloud Functions ───────────────────────────────────────────
header "Phase 3 — Deploying Cloud Functions"

SA_EMAIL="mag10-functions-sa@${GCP_PROJECT_ID}.iam.gserviceaccount.com"

# Copy shared/ into each function directory; clean up on exit
for fn in archive gcs_to_bq; do
  cp -r "${FUNCTIONS_DIR}/shared" "${FUNCTIONS_DIR}/${fn}/shared"
done
cleanup() {
  for fn in archive gcs_to_bq; do rm -rf "${FUNCTIONS_DIR}/${fn}/shared"; done
}
trap cleanup EXIT

# Deploy archive (HTTP trigger — receives Pub/Sub push payloads)
info "Deploying mag10-archive ..."
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
  --set-env-vars="GCS_BUCKET_RAW=mag-10-raw" \
  --quiet
ok "mag10-archive deployed"

# Deploy gcs-to-bq (Eventarc GCS trigger)
info "Deploying mag10-gcs-to-bq ..."
gcloud functions deploy mag10-gcs-to-bq \
  --gen2 \
  --project="${GCP_PROJECT_ID}" \
  --region="${REGION}" \
  --runtime=python312 \
  --source="${FUNCTIONS_DIR}/gcs_to_bq" \
  --entry-point=handle \
  --trigger-event-filters="type=google.cloud.storage.object.v1.finalized" \
  --trigger-event-filters="bucket=mag-10-raw" \
  --trigger-location="${REGION}" \
  --service-account="${SA_EMAIL}" \
  --memory=256Mi \
  --timeout=120s \
  --set-env-vars="GCP_PROJECT_ID=${GCP_PROJECT_ID},BQ_DATASET=${BQ_DATASET}" \
  --quiet
ok "mag10-gcs-to-bq deployed"

# ── Phase 4: Wire push subscription ───────────────────────────────────────────
header "Phase 4 — Terraform: enabling push delivery"

ARCHIVE_URL=$(gcloud functions describe mag10-archive \
  --gen2 \
  --project="${GCP_PROJECT_ID}" \
  --region="${REGION}" \
  --format="value(serviceConfig.uri)")

info "Archive URL: ${ARCHIVE_URL}"

cd "${INFRA_DIR}"

# Update archive_function_url in terraform.tfvars (add or replace)
if grep -q "^archive_function_url" terraform.tfvars 2>/dev/null; then
  sed -i '' "s|^archive_function_url.*|archive_function_url = \"${ARCHIVE_URL}\"|" terraform.tfvars
else
  echo "archive_function_url = \"${ARCHIVE_URL}\"" >> terraform.tfvars
fi

terraform apply -auto-approve -input=false

ok "Push subscription wired"

# ── Done ──────────────────────────────────────────────────────────────────────
cd "${REPO_ROOT}"

echo ""
echo -e "${BOLD}${GREEN}Deployment complete.${RESET}"
echo ""
DASHBOARD_URL=$(cd "${INFRA_DIR}" && terraform output -raw dashboard_url 2>/dev/null || echo "(run terraform output dashboard_url)")
echo -e "  Dashboard   → ${DASHBOARD_URL}"
echo -e "  WebSocket VM → $(cd "${INFRA_DIR}" && terraform output -raw websocket_vm_name 2>/dev/null)"
echo -e "  Detection VM → $(cd "${INFRA_DIR}" && terraform output -raw detection_vm_name 2>/dev/null)"
echo ""
