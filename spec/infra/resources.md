# Spec: Infrastructure Resources

## Principles

- All GCP resources are defined in Terraform under `infra/`.
- No resources are created manually in the GCP console.
- Naming convention: `mag10-{resource-type}-{env}` where `env` is `prod` or `dev`.
- Secrets are stored in GCP Secret Manager; never in Terraform state or source code.
- The Terraform state backend is GCS (bucket defined outside this project).

---

## GCP Project

| Item | Value |
|---|---|
| Project ID | `data-engineering-hs` |
| Region | `asia-southeast1` (Singapore) |

---

## Terraform Module Map

```
infra/
├── main.tf            # Root — calls all modules
├── variables.tf       # Input variables
├── outputs.tf         # Outputs
└── modules/
    ├── vm/            # Two Compute Engine VMs (WebSocket + Detection)
    ├── pubsub/        # Pub/Sub topics and subscriptions
    ├── bigquery/      # BigQuery dataset and tables
    └── gcs/           # GCS bucket
```

---

## Compute Engine VMs (modules/vm)

Two VMs, both e2-micro.

### WebSocket VM

| Attribute | Value |
|---|---|
| Name | `mag10-websocket-vm-prod` |
| Machine type | `e2-micro` |
| Zone | `asia-southeast1-b` |
| OS image | `cos-cloud/cos-stable` |
| Container image | `mag10-images/websocket:latest` from Artifact Registry |
| Service account | `mag10-websocket-sa` |
| External IP | Ephemeral (required for outbound WebSocket to Finnhub) |

**Service account roles:**
- `roles/pubsub.publisher` — publish to `mag10-raw-trades`
- `roles/secretmanager.secretAccessor` — read `mag10-finnhub-key`
- `roles/logging.logWriter`
- `roles/artifactregistry.reader`

### Detection VM

| Attribute | Value |
|---|---|
| Name | `mag10-detection-vm-prod` |
| Machine type | `e2-micro` |
| Zone | `asia-southeast1-b` |
| OS image | `cos-cloud/cos-stable` |
| Container image | `mag10-images/detection:latest` from Artifact Registry |
| Service account | `mag10-detection-sa` |
| External IP | Ephemeral (required for outbound Pub/Sub pull) |

**Service account roles:**
- `roles/pubsub.subscriber` — pull from `mag10-raw-trades-detection-sub`
- `roles/pubsub.publisher` — publish to `mag10-processed-signals`
- `roles/storage.objectViewer` — read Bronze from GCS for warm-start
- `roles/logging.logWriter`
- `roles/artifactregistry.reader`

---

## Pub/Sub (modules/pubsub)

### Topics

| Topic ID | Published by | Message retention |
|---|---|---|
| `mag10-raw-trades` | WebSocket VM | 7 days |
| `mag10-processed-signals` | Detection VM | 7 days |

### Subscriptions

| Subscription ID | Topic | Type | Delivers to |
|---|---|---|---|
| `mag10-raw-trades-bronze-sub` | `mag10-raw-trades` | Cloud Storage | GCS `bronze/` prefix |
| `mag10-raw-trades-detection-sub` | `mag10-raw-trades` | Pull | Detection VM |
| `mag10-processed-signals-sub` | `mag10-processed-signals` | Push | CF archive URL |

**Cloud Storage subscription settings (`mag10-raw-trades-bronze-sub`):**
- Bucket: `mag-10-raw`
- Object prefix: `bronze/`
- Max duration: 1 second
- Filename suffix: `.json`

**Pull subscription settings (`mag10-raw-trades-detection-sub`):**
- Ack deadline: 60 seconds
- Message retention: 7 days
- Retry policy: exponential backoff, 10s–600s

**Push subscription settings (`mag10-processed-signals-sub`):**
- Ack deadline: 60 seconds
- Message retention: 7 days
- Retry policy: exponential backoff, 10s–600s
- Dead-letter topic: none

---

## Cloud Functions (modules/functions)

Two functions, both Gen 2.

| Function name | Trigger | Service account |
|---|---|---|
| `mag10-cf-archive` | Pub/Sub push (`mag10-processed-signals-sub`) | `mag10-functions-sa` |
| `mag10-cf-gcs-to-bq` | GCS object finalise (`silver/`) | `mag10-functions-sa` |

**Shared function settings:**
- Runtime: Python 3.12
- Memory: 256 MB
- Timeout: 60 seconds
- Min instances: 0
- Region: `asia-southeast1`

**Service account roles (`mag10-functions-sa`):**
- `roles/storage.objectCreator` — write to GCS Silver (`cf-archive`)
- `roles/storage.objectViewer` — read from GCS Silver (`cf-gcs-to-bq`)
- `roles/bigquery.dataEditor` — stream insert to BQ (`cf-gcs-to-bq`)
- `roles/logging.logWriter`
- `roles/run.invoker` — allows Pub/Sub push to invoke the function

---

## BigQuery (modules/bigquery)

### Dataset

| Attribute | Value |
|---|---|
| Dataset ID | Controlled by `var.bq_dataset` (default: `signals`) |
| Location | `asia-southeast1` |
| Default table expiry | None |

### Tables

| Table ID | Partition field | Partition type | Cluster fields |
|---|---|---|---|
| `volume_spikes` | `timestamp` | DAY | `symbol` |
| `momentum_signals` | `window_end_ts` | DAY | `symbol`, `direction` |
| `volatility_spikes` | `timestamp` | DAY | `symbol` |
| `sector_snapshots` | `snapshot_ts` | DAY | `symbol` |

Full column definitions are in `spec/pipeline/bigquery.md`.

---

## GCS (modules/gcs)

### Single bucket, two prefixes

| Attribute | Value |
|---|---|
| Bucket name | `mag-10-raw` |
| Location | `asia-southeast1` |
| Storage class | `STANDARD` |
| Versioning | Disabled |
| Public access | Blocked |

| Prefix | Written by | Contents | Retention |
|---|---|---|---|
| `bronze/` | Pub/Sub Cloud Storage sub | Raw validated trades | 90 days |
| `silver/` | CF archive | Detected signals (JSON) | 90 days |

Lifecycle rules delete objects in both prefixes after 90 days.

---

## Secret Manager

| Secret name | Consumed by | Description |
|---|---|---|
| `mag10-finnhub-key` | WebSocket VM | Finnhub API key |
| `mag10-dashboard-password` | Dashboard (Cloud Run) | Dashboard login password |

Terraform creates the secret resources (empty). Values are added via
`gcloud secrets versions add` outside of Terraform.

---

## Artifact Registry

| Repository name | Format | Region |
|---|---|---|
| `mag10-images` | Docker | `asia-southeast1` |

Images stored:
- `mag10-images/websocket:latest` — WebSocket VM container
- `mag10-images/detection:latest` — Detection VM container
- `mag10-images/dashboard:latest` — Streamlit dashboard container

---

## Variables (`infra/variables.tf`)

| Variable | Type | Default | Description |
|---|---|---|---|
| `gcp_project_id` | string | (required) | GCP project ID |
| `region` | string | `asia-southeast1` | Default region |
| `zone` | string | `asia-southeast1-b` | VM zone |
| `env` | string | `prod` | Environment suffix |
| `bq_dataset` | string | `signals` | BigQuery dataset ID |
| `websocket_image` | string | (required) | WebSocket VM Docker image URI |
| `detection_image` | string | (required) | Detection VM Docker image URI |
| `dashboard_image` | string | (required) | Dashboard Docker image URI |
| `volume_function_url` | string | (required) | CF archive URL (for Pub/Sub push sub) |
| `gcs_to_bq_function_url` | string | (required) | CF gcs-to-bq URL |

---

## Outputs (`infra/outputs.tf`)

| Output | Description |
|---|---|
| `websocket_vm_name` | WebSocket VM instance name |
| `detection_vm_name` | Detection VM instance name |
| `pubsub_topics` | Map of topic name → full topic path |
| `bq_dataset_id` | BigQuery dataset ID |
| `gcs_bucket` | GCS bucket name |
| `artifact_registry_repo` | Artifact Registry repository URL |
| `dashboard_url` | Cloud Run dashboard service URL |
