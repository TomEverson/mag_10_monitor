# Spec: Infrastructure Resources

## Principles

- All GCP resources are defined in Terraform under `infra/`.
- No resources are created manually in the GCP console.
- Naming convention: `mag10-{resource-type}-{env}` where `env` is `prod` or `dev`.
- Secrets are stored in GCP Secret Manager; never in Terraform state or source code.
- The Terraform state backend is GCS (bucket defined outside this project).

---

## GCP Project

| Item        | Value |
|-------------|-------|
| Project ID  | Controlled by `var.gcp_project_id` |
| Region      | `us-central1` (default; overridable via `var.region`) |

---

## Terraform Module Map

```
infra/
├── main.tf            # Root — calls all modules
├── variables.tf       # Input variables
├── outputs.tf         # Outputs (e.g. Pub/Sub topic names, BQ dataset ID)
└── modules/
    ├── vm/            # Compute Engine VM (listener)
    ├── pubsub/        # Pub/Sub topics and subscriptions
    ├── bigquery/      # BigQuery dataset and tables
    └── gcs/           # GCS buckets
```

---

## Compute Engine VM (modules/vm)

| Attribute          | Value |
|--------------------|-------|
| Machine type       | `e2-micro` |
| Zone               | `us-central1-a` |
| OS image           | `cos-cloud/cos-stable` (Container-Optimised OS) |
| Container image    | Docker image from Artifact Registry |
| Service account    | `mag10-listener-sa` with Pub/Sub Publisher role |
| Network            | Default VPC |
| External IP        | Ephemeral (needed for outbound WebSocket to Finnhub) |
| Startup script     | Pulls and runs the listener container |
| Metadata           | `FINNHUB_API_KEY` secret version reference |

**Service account roles:**
- `roles/pubsub.publisher` — publish to all four topics
- `roles/secretmanager.secretAccessor` — read `FINNHUB_API_KEY`

---

## Pub/Sub (modules/pubsub)

### Topics

| Resource name              | Topic ID                   |
|----------------------------|----------------------------|
| `mag10-volume-spike`       | `mag10-volume-spike`       |
| `mag10-momentum-signal`    | `mag10-momentum-signal`    |
| `mag10-volatility-spike`   | `mag10-volatility-spike`   |
| `mag10-sector-snapshot`    | `mag10-sector-snapshot`    |

All topics use the default message retention (7 days).

### Subscriptions

| Subscription ID               | Topic                      | Delivery | Endpoint |
|-------------------------------|----------------------------|----------|----------|
| `mag10-volume-spike-sub`      | `mag10-volume-spike`       | Push     | Cloud Function URL |
| `mag10-momentum-signal-sub`   | `mag10-momentum-signal`    | Push     | Cloud Function URL |
| `mag10-volatility-spike-sub`  | `mag10-volatility-spike`   | Push     | Cloud Function URL |
| `mag10-sector-snapshot-sub`   | `mag10-sector-snapshot`    | Push     | Cloud Function URL |

Subscription settings:
- Ack deadline: 60 seconds
- Message retention: 7 days
- Dead-letter topic: none (retry is sufficient; messages expire after 7 days)
- Retry policy: exponential backoff, 10s–600s

---

## BigQuery (modules/bigquery)

### Dataset

| Attribute        | Value |
|-----------------|-------|
| Dataset ID       | Controlled by `var.bq_dataset` (default: `signals`) |
| Location         | `US` |
| Default table expiry | None (data retained indefinitely) |

### Tables

Created by Terraform using schema JSON files co-located with the module.

| Table ID             | Schema file              | Partition field | Partition type | Cluster fields |
|----------------------|--------------------------|-----------------|----------------|----------------|
| `volume_spikes`      | `schema_volume.json`     | `timestamp`     | DAY            | `symbol`       |
| `momentum_signals`   | `schema_momentum.json`   | `timestamp`     | DAY            | `symbol`, `direction` |
| `volatility_spikes`  | `schema_volatility.json` | `timestamp`     | DAY            | `symbol`       |
| `sector_snapshots`   | `schema_sector.json`     | `snapshot_ts`   | DAY            | `symbol`       |

Full column definitions are in `spec/pipeline/bigquery.md`.

**Service account for Cloud Functions:**  
`mag10-functions-sa` with `roles/bigquery.dataEditor` on the dataset.

---

## GCS (modules/gcs)

### Raw event archive bucket

| Attribute       | Value |
|-----------------|-------|
| Bucket name     | `mag10-raw-{gcp_project_id}` (globally unique via project ID suffix) |
| Location        | `US-CENTRAL1` |
| Storage class   | `STANDARD` |
| Lifecycle rule  | Delete objects older than 90 days |
| Versioning      | Disabled |
| Public access   | Blocked |

Object path conventions are defined in `spec/pipeline/functions.md`.

**Service account:**  
`mag10-functions-sa` with `roles/storage.objectCreator` on this bucket.

---

## Secret Manager

Secrets are created and versioned manually (not by Terraform) to avoid storing
secret values in Terraform state.

| Secret name         | Consumed by | Description |
|---------------------|-------------|-------------|
| `mag10-finnhub-key` | VM listener | Finnhub API key |

Terraform creates the secret resource (empty); the actual value is added via
`gcloud secrets versions add` outside of Terraform.

---

## Artifact Registry

| Repository name | Format | Region       |
|-----------------|--------|--------------|
| `mag10-images`  | Docker | `us-central1` |

The listener Docker image is pushed here and referenced by the VM startup
configuration.

---

## Variables (`infra/variables.tf`)

| Variable            | Type   | Default       | Description |
|---------------------|--------|---------------|-------------|
| `gcp_project_id`    | string | (required)    | GCP project ID |
| `region`            | string | `us-central1` | Default region |
| `zone`              | string | `us-central1-a` | VM zone |
| `env`               | string | `prod`        | Environment suffix for resource names |
| `bq_dataset`        | string | `signals`     | BigQuery dataset ID |
| `listener_image`    | string | (required)    | Full Docker image URI for the listener |

---

## Outputs (`infra/outputs.tf`)

| Output                  | Description |
|-------------------------|-------------|
| `vm_name`               | Compute Engine instance name |
| `pubsub_topics`         | Map of topic name → full topic path |
| `bq_dataset_id`         | BigQuery dataset ID |
| `gcs_raw_bucket`        | GCS raw archive bucket name |
| `artifact_registry_repo`| Artifact Registry repository URL |
