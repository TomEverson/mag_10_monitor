# mag10-monitor

Real-time market intelligence pipeline for MAG 7 + AMD, AVGO, PLTR. Ingests live trades via Finnhub WebSocket, detects four signal types, and surfaces them on a Streamlit dashboard backed by BigQuery — all on a single GCP e2-micro VM, four Cloud Functions, and one Cloud Run service.

## Architecture

```
Finnhub WebSocket
      │
      ▼
listener/ (e2-micro VM)
  • Volume spike detector
  • Momentum signal detector
  • Volatility spike detector
  • Sector snapshot (every 60s)
      │
      ├──► Pub/Sub: mag10-volume-spike
      ├──► Pub/Sub: mag10-momentum-signal
      ├──► Pub/Sub: mag10-volatility-spike
      └──► Pub/Sub: mag10-sector-snapshot
                │
                ▼
         Cloud Functions (one per topic)
           • Validates payload
           • Archives raw event to GCS
           • Streams row to BigQuery
                │
                ▼
           BigQuery (dataset: signals)
                │
                ▼
           Streamlit Dashboard (Cloud Run)
```

## Prerequisites

- GCP project with billing enabled
- [`gcloud` CLI](https://cloud.google.com/sdk/docs/install) authenticated (`gcloud auth login`)
- [Terraform](https://developer.hashicorp.com/terraform/install) >= 1.6
- [uv](https://docs.astral.sh/uv/getting-started/installation/) (Python package manager)
- [Docker](https://docs.docker.com/get-docker/) (for building the listener image)
- A [Finnhub](https://finnhub.io) API key (free tier is sufficient)

## Deployment

Deployment is a five-step process. Steps 1–3 provision GCP infrastructure, step 4 deploys the listener, and step 5 deploys the Cloud Functions and wires them to Pub/Sub.

### Step 1 — Create a Terraform state bucket

This bucket is managed outside Terraform and must exist before `terraform init`.

```bash
gsutil mb -p YOUR_PROJECT_ID gs://YOUR_TF_STATE_BUCKET
```

Uncomment the `backend "gcs"` block in `infra/main.tf` and set the bucket name.

### Step 2 — Provision GCP infrastructure

```bash
cd infra

cat > terraform.tfvars <<EOF
gcp_project_id = "YOUR_PROJECT_ID"
listener_image = "us-central1-docker.pkg.dev/YOUR_PROJECT_ID/mag10-images/listener:latest"
EOF

terraform init
terraform apply
```

This creates Pub/Sub topics (in pull mode), BigQuery tables, GCS bucket, Artifact Registry, VM, and service accounts.

### Step 3 — Store the Finnhub API key

```bash
echo -n "YOUR_FINNHUB_KEY" | \
  gcloud secrets versions add mag10-finnhub-key \
    --project=YOUR_PROJECT_ID \
    --data-file=-
```

### Step 4 — Build and push the listener image

```bash
cd listener

REGION=us-central1
PROJECT_ID=YOUR_PROJECT_ID
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/mag10-images/listener:latest"

gcloud auth configure-docker "${REGION}-docker.pkg.dev"
docker build -t "${IMAGE}" .
docker push "${IMAGE}"
```

The VM will pull and run this image on startup. To restart the VM after a new image push:

```bash
gcloud compute instances reset mag10-listener-vm-prod \
  --project=YOUR_PROJECT_ID --zone=us-central1-a
```

### Step 5 — Deploy Cloud Functions and enable push delivery

```bash
export GCP_PROJECT_ID=YOUR_PROJECT_ID
./scripts/deploy_functions.sh
```

The script copies `functions/shared/` into each function directory, deploys all four functions, and prints the four function URLs. Add them to `infra/terraform.tfvars`:

```hcl
volume_function_url     = "https://..."
momentum_function_url   = "https://..."
volatility_function_url = "https://..."
sector_function_url     = "https://..."
```

Then re-apply Terraform to switch Pub/Sub subscriptions from pull to push:

```bash
cd infra && terraform apply
```

## Dashboard

The dashboard is a Streamlit app deployed on Cloud Run. Build and push the image, then set `dashboard_image` in `infra/terraform.tfvars` and re-apply Terraform.

```bash
cd dashboard

REGION=us-central1
PROJECT_ID=YOUR_PROJECT_ID
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/mag10-images/dashboard:latest"

gcloud auth configure-docker "${REGION}-docker.pkg.dev"
docker build -t "${IMAGE}" .
docker push "${IMAGE}"
```

Set the dashboard password:

```bash
echo -n "yourpassword" | \
  gcloud secrets versions add mag10-dashboard-password \
    --project=YOUR_PROJECT_ID \
    --data-file=-
```

Then add to `infra/terraform.tfvars`:

```hcl
dashboard_image = "us-central1-docker.pkg.dev/YOUR_PROJECT_ID/mag10-images/dashboard:latest"
```

And re-apply:

```bash
cd infra && terraform apply
```

The dashboard URL is printed as a Terraform output. It has six tabs: Live Signals, Volume Analysis, Momentum & Correlation, Volatility & Sector, Analytics, and News & Sentiment.

## Local development

### Listener

```bash
cd listener
cp .env.example .env      # fill in your values
uv sync
uv run python main.py
```

### Cloud Functions

Each function can be tested locally with the Functions Framework:

```bash
cd functions/volume
cp -r ../shared ./shared  # required at runtime
uv sync
uv run functions-framework --target=handle --debug
```

Send a test request:

```bash
curl -X POST http://localhost:8080 \
  -H "Content-Type: application/json" \
  -d '{"message": {"data": "<base64-encoded-payload>"}}'
```

## Repository layout

```
mag10-monitor/
├── spec/            # Source of truth — read before modifying code
├── listener/        # WebSocket listener (runs on e2-micro VM)
│   └── detectors/   # Volume, momentum, volatility, sector detectors
├── functions/       # Cloud Functions — one per Pub/Sub topic
│   └── shared/      # Pydantic models + BigQuery client (copied at deploy time)
├── infra/           # Terraform — all GCP resources
│   └── modules/     # vm, pubsub, bigquery, gcs
├── dashboard/       # Streamlit app (Cloud Run)
│   ├── streamlit_app.py  # UI — 6 tabs
│   └── queries.py        # BigQuery query functions
└── scripts/
    └── deploy_functions.sh
```

## Updating dependencies

Each service manages its own isolated environment.

```bash
# Add a dependency to a function
cd functions/volume
uv add some-package
uv pip compile pyproject.toml -o requirements.txt   # regenerate for GCP

# Add a dependency to the listener
cd listener
uv add some-package
```

Never edit `requirements.txt` by hand. Never use `pip` directly.
