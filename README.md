# mag10-monitor

Real-time market intelligence pipeline for MAG 7 + AMD, AVGO, PLTR. Ingests live trades via Finnhub WebSocket, detects four signal types, archives them through a Bronze/Silver/Gold data lakehouse on GCS and BigQuery, and surfaces results on a Streamlit dashboard — all on GCP.

## Architecture

```
Finnhub WebSocket
      │
      ▼
websocket/ (e2-micro VM)
  Publishes raw trades: { s, p, v, t }
      │
      ▼
Pub/Sub: mag10-raw-trades
      │
      ├──► Bronze (Cloud Storage subscription)
      │      gs://mag-10-raw/bronze/YYYY-MM-DD...json
      │      Raw trade batches — used for warm-start on Detection VM restart
      │
      └──► Detection subscription (pull)
             │
             ▼
      detection/ (e2-micro VM)
        • Volume spike detector    (rolling window, in-RAM)
        • Momentum signal detector (rolling window, in-RAM)
        • Volatility spike detector(rolling window, in-RAM)
        • Sector snapshot          (every 60 s)
        Warm-starts from Bronze on restart
             │
             ▼
      Pub/Sub: mag10-processed-signals
             │
             ▼
      Archive subscription (push → CF)
             │
             ▼
      CF: mag10-archive                      Silver layer
        Validates payload (Pydantic)  ──►  gs://mag-10-raw/silver/{type}/YYYY/MM/DD/...json
        Routes by signal_type attribute
             │ (GCS object finalization trigger)
             ▼
      CF: mag10-gcs-to-bq                    Gold layer
        Routes by GCS path prefix    ──►  BigQuery dataset: signals
        Deterministic insertId               • volume_spikes
        (deduplication)                      • momentum_signals
                                             • volatility_spikes
                                             • sector_snapshots
                                                   │
                                                   ▼
                                        Streamlit Dashboard (Cloud Run)
```

## Data layers

| Layer | Location | Written by | Contents |
|-------|----------|-----------|----------|
| Bronze | `gs://mag-10-raw/bronze/` | Pub/Sub Cloud Storage subscription | Raw trade JSON batches, 60 s windows |
| Silver | `gs://mag-10-raw/silver/{type}/YYYY/MM/DD/` | CF `mag10-archive` | Validated processed signal JSON, one file per event |
| Gold | BigQuery `signals.*` | CF `mag10-gcs-to-bq` | Queryable signal tables with `processed_at` timestamps |

## Prerequisites

- GCP project with billing enabled
- [`gcloud` CLI](https://cloud.google.com/sdk/docs/install) authenticated (`gcloud auth login`)
- [Terraform](https://developer.hashicorp.com/terraform/install) >= 1.6
- [uv](https://docs.astral.sh/uv/getting-started/installation/) (Python package manager)
- A [Finnhub](https://finnhub.io) API key (free tier is sufficient)

## Deployment

Deployment is a two-phase process. Phase 1 provisions infrastructure and VMs; Phase 2 deploys Cloud Functions and switches Pub/Sub to push mode.

### Step 1 — Store secrets

```bash
# Finnhub API key (required by WebSocket VM)
echo -n "YOUR_FINNHUB_KEY" | \
  gcloud secrets versions add mag10-finnhub-key \
    --project=YOUR_PROJECT_ID --data-file=-

# Dashboard password
echo -n "yourpassword" | \
  gcloud secrets versions add mag10-dashboard-password \
    --project=YOUR_PROJECT_ID --data-file=-
```

### Step 2 — Build and push Docker images

Uses Cloud Build — no local Docker required.

```bash
PROJECT=YOUR_PROJECT_ID
REGION=asia-southeast1
REPO="${REGION}-docker.pkg.dev/${PROJECT}/mag10-images"

gcloud builds submit --project=$PROJECT --region=$REGION \
  --tag="${REPO}/websocket:latest" websocket/

gcloud builds submit --project=$PROJECT --region=$REGION \
  --tag="${REPO}/detection:latest" detection/

gcloud builds submit --project=$PROJECT --region=$REGION \
  --tag="${REPO}/dashboard:latest" dashboard/
```

### Step 3 — First Terraform apply (infrastructure + VMs)

```bash
cd infra

cat > terraform.tfvars <<EOF
gcp_project_id  = "YOUR_PROJECT_ID"
websocket_image = "asia-southeast1-docker.pkg.dev/YOUR_PROJECT_ID/mag10-images/websocket:latest"
detection_image = "asia-southeast1-docker.pkg.dev/YOUR_PROJECT_ID/mag10-images/detection:latest"
dashboard_image = "asia-southeast1-docker.pkg.dev/YOUR_PROJECT_ID/mag10-images/dashboard:latest"
EOF

terraform init
terraform apply
```

This creates: Pub/Sub topics and subscriptions (archive in pull mode), GCS bucket, BigQuery tables, Artifact Registry, both VMs, service accounts, and Cloud Run dashboard.

### Step 4 — Deploy Cloud Functions

```bash
export GCP_PROJECT_ID=YOUR_PROJECT_ID
./scripts/deploy_functions.sh
```

The script deploys both functions and prints the archive function URL:

```
archive_function_url = "https://mag10-archive-<hash>-as.a.run.app"
```

### Step 5 — Second Terraform apply (enable push delivery)

Add the archive URL to `infra/terraform.tfvars`:

```hcl
archive_function_url = "https://mag10-archive-<hash>-as.a.run.app"
```

Then re-apply to switch the Pub/Sub subscription from pull to push:

```bash
cd infra && terraform apply
```

The pipeline is now fully live.

## Repository layout

```
mag10-monitor/
├── spec/              # Source of truth — read before modifying code
├── websocket/         # Finnhub WebSocket ingest service (e2-micro VM)
├── detection/         # Signal detection service (e2-micro VM)
│   └── detectors/     # Volume, momentum, volatility, sector detectors
├── functions/
│   ├── archive/       # CF: Pub/Sub push → GCS Silver
│   ├── gcs_to_bq/     # CF: GCS finalization → BigQuery
│   └── shared/        # Pydantic models + BigQuery client (copied at deploy time)
├── dashboard/         # Streamlit app (Cloud Run)
│   ├── streamlit_app.py
│   └── queries.py
├── infra/             # Terraform — all GCP resources
│   └── modules/       # vm, pubsub, bigquery, gcs
└── scripts/
    └── deploy_functions.sh
```

## Rebuilding a service

After code changes, rebuild the image and reset the VM:

```bash
# Rebuild (e.g. websocket)
gcloud builds submit --project=$PROJECT --region=$REGION \
  --tag="${REPO}/websocket:latest" websocket/

# Reset VM to pull new image
gcloud compute instances reset mag10-websocket-prod \
  --project=$PROJECT --zone=asia-southeast1-b
```

For Cloud Functions, re-run `./scripts/deploy_functions.sh`.

## Local development

```bash
# WebSocket service
cd websocket
cp .env.example .env   # fill in values
uv sync
uv run python main.py

# Detection service
cd detection
cp .env.example .env
uv sync
uv run python main.py

# Archive function (local testing)
cd functions/archive
cp -r ../shared ./shared
uv sync
uv run functions-framework --target=handle --debug
```

## Dependency management

Each service manages its own isolated environment with `uv`. Never use `pip` directly and never edit `requirements.txt` by hand.

```bash
# Add a dependency
cd websocket
uv add some-package

# Regenerate requirements.txt for Cloud Functions deploy
cd functions/archive
uv pip compile pyproject.toml -o requirements.txt
```
