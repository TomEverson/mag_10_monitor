terraform {
  required_version = ">= 1.6"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }

  # Configure the GCS backend before running terraform init.
  # The state bucket must exist before init and is managed outside this project.
  # backend "gcs" {
  #   bucket = "your-tf-state-bucket"
  #   prefix = "mag10-monitor"
  # }
}

provider "google" {
  project = var.gcp_project_id
  region  = var.region
}

# ── APIs ──────────────────────────────────────────────────────────────────────

locals {
  required_apis = [
    "pubsub.googleapis.com",
    "bigquery.googleapis.com",
    "storage.googleapis.com",
    "compute.googleapis.com",
    "secretmanager.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudfunctions.googleapis.com",
    "run.googleapis.com",
    "cloudbuild.googleapis.com",
    "eventarc.googleapis.com",
  ]

  detection_startup_script = <<-EOT
    #!/bin/bash
    set -e

    TOKEN=$(curl -sf "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token" \
      -H "Metadata-Flavor: Google" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

    export DOCKER_CONFIG=/tmp/docker-config
    mkdir -p $DOCKER_CONFIG
    echo "$TOKEN" | docker login -u oauth2accesstoken --password-stdin ${var.region}-docker.pkg.dev

    docker pull ${var.detection_image}
    docker rm -f mag10-detection 2>/dev/null || true

    docker run -d \
      --name mag10-detection \
      --restart always \
      --log-driver=gcplogs \
      --log-opt gcp-project=${var.gcp_project_id} \
      -e GCP_PROJECT_ID="${var.gcp_project_id}" \
      -e GCS_BUCKET="${module.gcs.bucket_name}" \
      -e PUBSUB_SUBSCRIPTION_RAW="${module.pubsub.detection_subscription_name}" \
      -e PUBSUB_TOPIC_PROCESSED="${module.pubsub.processed_signals_topic_name}" \
      ${var.detection_image}
  EOT
}

resource "google_project_service" "apis" {
  for_each           = toset(local.required_apis)
  service            = each.value
  disable_on_destroy = false
}

# ── Service accounts ──────────────────────────────────────────────────────────

resource "google_service_account" "websocket" {
  account_id   = "mag10-websocket-sa"
  display_name = "MAG10 WebSocket"
  description  = "Used by the e2-micro VM running the Finnhub WebSocket ingest service"
}

resource "google_service_account" "detection" {
  account_id   = "mag10-detection-sa"
  display_name = "MAG10 Detection"
  description  = "Used by the e2-micro VM running the signal detection service"
}

resource "google_service_account" "functions" {
  account_id   = "mag10-functions-sa"
  display_name = "MAG10 Cloud Functions"
  description  = "Used by the archive and gcs-to-bq Cloud Functions"
}

resource "google_service_account" "dashboard" {
  account_id   = "mag10-dashboard-sa"
  display_name = "MAG10 Dashboard"
  description  = "Used by the Cloud Run dashboard service"
}

# ── IAM — websocket SA ────────────────────────────────────────────────────────

resource "google_project_iam_member" "websocket_pubsub_publisher" {
  project = var.gcp_project_id
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${google_service_account.websocket.email}"
}

resource "google_project_iam_member" "websocket_secret_accessor" {
  project = var.gcp_project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.websocket.email}"
}

resource "google_project_iam_member" "websocket_log_writer" {
  project = var.gcp_project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.websocket.email}"
}

resource "google_project_iam_member" "websocket_ar_reader" {
  project = var.gcp_project_id
  role    = "roles/artifactregistry.reader"
  member  = "serviceAccount:${google_service_account.websocket.email}"
}

# ── IAM — detection SA ────────────────────────────────────────────────────────

resource "google_project_iam_member" "detection_pubsub_subscriber" {
  project = var.gcp_project_id
  role    = "roles/pubsub.subscriber"
  member  = "serviceAccount:${google_service_account.detection.email}"
}

resource "google_project_iam_member" "detection_pubsub_publisher" {
  project = var.gcp_project_id
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${google_service_account.detection.email}"
}

resource "google_project_iam_member" "detection_gcs_viewer" {
  project = var.gcp_project_id
  role    = "roles/storage.objectViewer"
  member  = "serviceAccount:${google_service_account.detection.email}"
}

resource "google_project_iam_member" "detection_log_writer" {
  project = var.gcp_project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.detection.email}"
}

resource "google_project_iam_member" "detection_ar_reader" {
  project = var.gcp_project_id
  role    = "roles/artifactregistry.reader"
  member  = "serviceAccount:${google_service_account.detection.email}"
}

# ── IAM — functions SA ───────────────────────────────────────────────────────

resource "google_project_iam_member" "functions_bq_editor" {
  project = var.gcp_project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${google_service_account.functions.email}"
}

# archive CF writes Silver files; gcs-to-bq CF reads them
resource "google_project_iam_member" "functions_gcs_creator" {
  project = var.gcp_project_id
  role    = "roles/storage.objectCreator"
  member  = "serviceAccount:${google_service_account.functions.email}"
}

resource "google_project_iam_member" "functions_gcs_viewer" {
  project = var.gcp_project_id
  role    = "roles/storage.objectViewer"
  member  = "serviceAccount:${google_service_account.functions.email}"
}

resource "google_project_iam_member" "functions_log_writer" {
  project = var.gcp_project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.functions.email}"
}

# Required for GCS Eventarc trigger on the gcs-to-bq function
resource "google_project_iam_member" "functions_eventarc_receiver" {
  project = var.gcp_project_id
  role    = "roles/eventarc.eventReceiver"
  member  = "serviceAccount:${google_service_account.functions.email}"
}

# GCS service agent must publish Pub/Sub events for Eventarc GCS triggers
resource "google_project_iam_member" "gcs_sa_pubsub_publisher" {
  project = var.gcp_project_id
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:service-214081441484@gs-project-accounts.iam.gserviceaccount.com"
}

# Allows Pub/Sub push subscriptions to invoke Cloud Run-backed functions via OIDC
resource "google_project_iam_member" "functions_run_invoker" {
  project = var.gcp_project_id
  role    = "roles/run.invoker"
  member  = "serviceAccount:${google_service_account.functions.email}"
}

# Allows the Pub/Sub service agent to generate OIDC tokens for mag10-functions-sa
resource "google_service_account_iam_member" "pubsub_token_creator" {
  service_account_id = google_service_account.functions.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:service-214081441484@gcp-sa-pubsub.iam.gserviceaccount.com"
}

# ── IAM — dashboard SA ───────────────────────────────────────────────────────

resource "google_project_iam_member" "dashboard_bq_viewer" {
  project = var.gcp_project_id
  role    = "roles/bigquery.dataViewer"
  member  = "serviceAccount:${google_service_account.dashboard.email}"
}

resource "google_project_iam_member" "dashboard_bq_job_user" {
  project = var.gcp_project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.dashboard.email}"
}

resource "google_project_iam_member" "dashboard_bq_read_session" {
  project = var.gcp_project_id
  role    = "roles/bigquery.readSessionUser"
  member  = "serviceAccount:${google_service_account.dashboard.email}"
}

resource "google_project_iam_member" "dashboard_secret_accessor" {
  project = var.gcp_project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.dashboard.email}"
}

# ── Secret Manager ────────────────────────────────────────────────────────────
# Add the actual value with:
#   gcloud secrets versions add mag10-finnhub-key --data-file=-
#   echo -n "yourpassword" | gcloud secrets versions add mag10-dashboard-password --data-file=-

resource "google_secret_manager_secret" "finnhub_key" {
  secret_id = "mag10-finnhub-key"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret" "dashboard_password" {
  secret_id = "mag10-dashboard-password"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

# ── Artifact Registry ─────────────────────────────────────────────────────────

resource "google_artifact_registry_repository" "images" {
  location      = var.region
  repository_id = "mag10-images"
  format        = "DOCKER"
  description   = "Docker images for MAG10 monitor services"
  depends_on    = [google_project_service.apis]
}

# ── Modules ───────────────────────────────────────────────────────────────────

module "gcs" {
  source = "./modules/gcs"

  project_id = var.gcp_project_id
  region     = var.region

  depends_on = [google_project_service.apis]
}

# Pub/Sub Cloud Storage subscription writes Bronze files; the Pub/Sub service
# agent needs both legacyBucketReader and objectCreator at the bucket level.
resource "google_storage_bucket_iam_member" "pubsub_gcs_creator" {
  bucket = module.gcs.bucket_name
  role   = "roles/storage.objectCreator"
  member = "serviceAccount:service-214081441484@gcp-sa-pubsub.iam.gserviceaccount.com"
}

resource "google_storage_bucket_iam_member" "pubsub_gcs_reader" {
  bucket = module.gcs.bucket_name
  role   = "roles/storage.legacyBucketReader"
  member = "serviceAccount:service-214081441484@gcp-sa-pubsub.iam.gserviceaccount.com"
}

module "pubsub" {
  source = "./modules/pubsub"

  functions_sa_email   = google_service_account.functions.email
  gcs_bucket           = module.gcs.bucket_name
  gcs_bucket_resource  = module.gcs
  archive_function_url = var.archive_function_url

  depends_on = [
    google_project_service.apis,
    google_storage_bucket_iam_member.pubsub_gcs_creator,
    google_storage_bucket_iam_member.pubsub_gcs_reader,
  ]
}

module "bigquery" {
  source = "./modules/bigquery"

  project_id = var.gcp_project_id
  dataset_id = var.bq_dataset

  depends_on = [google_project_service.apis]
}

module "vm" {
  source = "./modules/vm"

  project_id              = var.gcp_project_id
  region                  = var.region
  zone                    = var.zone
  env                     = var.env
  image                   = var.websocket_image
  service_account_email   = google_service_account.websocket.email
  pubsub_topic_raw_trades = module.pubsub.raw_trades_topic_name

  depends_on = [
    google_project_service.apis,
    google_secret_manager_secret.finnhub_key,
    module.pubsub,
  ]
}

# ── Detection VM ──────────────────────────────────────────────────────────────

resource "google_compute_instance" "detection" {
  name         = "mag10-detection-${var.env}"
  machine_type = "e2-micro"
  zone         = var.zone

  boot_disk {
    initialize_params {
      image = "cos-cloud/cos-stable"
      size  = 10
    }
  }

  network_interface {
    network = "default"
    access_config {}
  }

  service_account {
    email  = google_service_account.detection.email
    scopes = ["cloud-platform"]
  }

  metadata = {
    startup-script         = local.detection_startup_script
    google-logging-enabled = "true"
  }

  tags = ["mag10-detection"]

  lifecycle {
    replace_triggered_by = [
      terraform_data.detection_image_trigger
    ]
  }

  depends_on = [
    google_project_service.apis,
    module.pubsub,
  ]
}

resource "terraform_data" "detection_image_trigger" {
  input = var.detection_image
}

# ── Cloud Run — dashboard ─────────────────────────────────────────────────────

resource "google_cloud_run_v2_service" "dashboard" {
  name     = "mag10-dashboard"
  location = var.region

  template {
    service_account = google_service_account.dashboard.email

    scaling {
      min_instance_count = 0
      max_instance_count = 1
    }

    containers {
      image = var.dashboard_image

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          memory = "512Mi"
          cpu    = "1"
        }
      }

      env {
        name  = "GCP_PROJECT_ID"
        value = var.gcp_project_id
      }

      env {
        name  = "BQ_DATASET"
        value = var.bq_dataset
      }

      env {
        name = "DASHBOARD_PASSWORD"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.dashboard_password.secret_id
            version = "latest"
          }
        }
      }

      env {
        name = "FINNHUB_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.finnhub_key.secret_id
            version = "latest"
          }
        }
      }
    }
  }

  depends_on = [
    google_project_service.apis,
    google_project_iam_member.dashboard_bq_viewer,
    google_project_iam_member.dashboard_bq_job_user,
    google_project_iam_member.dashboard_bq_read_session,
    google_project_iam_member.dashboard_secret_accessor,
  ]
}

resource "google_cloud_run_v2_service_iam_member" "dashboard_public" {
  project  = google_cloud_run_v2_service.dashboard.project
  location = google_cloud_run_v2_service.dashboard.location
  name     = google_cloud_run_v2_service.dashboard.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
