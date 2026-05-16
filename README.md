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

### Step 1 — Store secrets

Do this once before the first deploy. The Secret Manager resources are created by Terraform but their values must be set manually.

```bash
# Finnhub API key (required by the WebSocket VM)
echo -n "YOUR_FINNHUB_KEY" | \
  gcloud secrets versions add mag10-finnhub-key \
    --project=YOUR_PROJECT_ID --data-file=-

# Dashboard password
echo -n "yourpassword" | \
  gcloud secrets versions add mag10-dashboard-password \
    --project=YOUR_PROJECT_ID --data-file=-
```

### Step 2 — Run the deploy script

```bash
export GCP_PROJECT_ID=YOUR_PROJECT_ID
./scripts/deploy.sh
```

That's it. The script handles everything in four phases:

| Phase | What it does |
|-------|-------------|
| 1 — Build images | Submits `websocket`, `detection`, and `dashboard` to Cloud Build in parallel (no local Docker needed) |
| 2 — Terraform | `terraform init && terraform apply` — provisions VMs, Pub/Sub, GCS, BigQuery, Cloud Run, IAM |
| 3 — Cloud Functions | Deploys `mag10-archive` (Pub/Sub push) and `mag10-gcs-to-bq` (GCS Eventarc trigger) |
| 4 — Wire push | Extracts the archive function URL, updates `terraform.tfvars`, re-applies to switch Pub/Sub to push mode |

On completion it prints:

```
Deployment complete.
  Dashboard   → https://mag10-dashboard-<hash>-as.a.run.app
  WebSocket VM → mag10-websocket-prod
  Detection VM → mag10-detection-prod
```

### Re-deploying after changes

```bash
# Code changed in one or more services — rebuild images and redeploy functions
export GCP_PROJECT_ID=YOUR_PROJECT_ID
./scripts/deploy.sh

# Infra-only change (no code changes) — skip image builds
./scripts/deploy.sh --skip-images

# Functions-only change — skip images and Terraform
./scripts/deploy.sh --skip-images --skip-tf
```

To reset a VM so it pulls the latest image immediately:

```bash
gcloud compute instances reset mag10-websocket-prod \
  --project=YOUR_PROJECT_ID --zone=asia-southeast1-b

gcloud compute instances reset mag10-detection-prod \
  --project=YOUR_PROJECT_ID --zone=asia-southeast1-b
```

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
    ├── deploy.sh            # Full deploy (images → terraform → functions → push wiring)
    └── deploy_functions.sh  # Functions-only deploy (called by deploy.sh)
```

## Rebuilding a service

After code changes run `./scripts/deploy.sh` (see flags above). To reset a VM manually without a full deploy:

```bash
gcloud compute instances reset mag10-websocket-prod \
  --project=YOUR_PROJECT_ID --zone=asia-southeast1-b
```

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
