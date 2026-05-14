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
  ]
}

resource "google_project_service" "apis" {
  for_each           = toset(local.required_apis)
  service            = each.value
  disable_on_destroy = false
}

# ── Service accounts ──────────────────────────────────────────────────────────

resource "google_service_account" "listener" {
  account_id   = "mag10-listener-sa"
  display_name = "MAG10 Listener"
  description  = "Used by the e2-micro VM running the Finnhub WebSocket listener"
}

resource "google_service_account" "functions" {
  account_id   = "mag10-functions-sa"
  display_name = "MAG10 Cloud Functions"
  description  = "Used by all four signal-processing Cloud Functions"
}

# ── IAM — listener SA ────────────────────────────────────────────────────────

resource "google_project_iam_member" "listener_pubsub_publisher" {
  project = var.gcp_project_id
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${google_service_account.listener.email}"
}

resource "google_project_iam_member" "listener_secret_accessor" {
  project = var.gcp_project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.listener.email}"
}

resource "google_project_iam_member" "listener_log_writer" {
  project = var.gcp_project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.listener.email}"
}

resource "google_project_iam_member" "listener_ar_reader" {
  project = var.gcp_project_id
  role    = "roles/artifactregistry.reader"
  member  = "serviceAccount:${google_service_account.listener.email}"
}

# ── IAM — functions SA ───────────────────────────────────────────────────────

resource "google_project_iam_member" "functions_bq_editor" {
  project = var.gcp_project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${google_service_account.functions.email}"
}

resource "google_project_iam_member" "functions_gcs_creator" {
  project = var.gcp_project_id
  role    = "roles/storage.objectCreator"
  member  = "serviceAccount:${google_service_account.functions.email}"
}

resource "google_project_iam_member" "functions_log_writer" {
  project = var.gcp_project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.functions.email}"
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

# ── Secret Manager ────────────────────────────────────────────────────────────
# Creates the secret resource only. Add the actual value with:
#   gcloud secrets versions add mag10-finnhub-key --data-file=-

resource "google_secret_manager_secret" "finnhub_key" {
  secret_id = "mag10-finnhub-key"
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

# ── Dashboard service account ─────────────────────────────────────────────────

resource "google_service_account" "dashboard" {
  account_id   = "mag10-dashboard-sa"
  display_name = "MAG10 Dashboard"
  description  = "Used by the Cloud Run dashboard service"
}

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

# ── Dashboard password secret ─────────────────────────────────────────────────
# After apply, set the value with:
#   echo -n "yourpassword" | gcloud secrets versions add mag10-dashboard-password --data-file=-

resource "google_secret_manager_secret" "dashboard_password" {
  secret_id = "mag10-dashboard-password"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
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

# Public access — password auth is handled inside the app
resource "google_cloud_run_v2_service_iam_member" "dashboard_public" {
  project  = google_cloud_run_v2_service.dashboard.project
  location = google_cloud_run_v2_service.dashboard.location
  name     = google_cloud_run_v2_service.dashboard.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# ── Modules ───────────────────────────────────────────────────────────────────

module "pubsub" {
  source = "./modules/pubsub"

  functions_sa_email      = google_service_account.functions.email
  volume_function_url     = var.volume_function_url
  momentum_function_url   = var.momentum_function_url
  volatility_function_url = var.volatility_function_url
  sector_function_url     = var.sector_function_url

  depends_on = [google_project_service.apis]
}

module "bigquery" {
  source = "./modules/bigquery"

  project_id = var.gcp_project_id
  dataset_id = var.bq_dataset

  depends_on = [google_project_service.apis]
}

module "gcs" {
  source = "./modules/gcs"

  project_id = var.gcp_project_id
  region     = var.region

  depends_on = [google_project_service.apis]
}

module "vm" {
  source = "./modules/vm"

  project_id            = var.gcp_project_id
  region                = var.region
  zone                  = var.zone
  env                   = var.env
  listener_image        = var.listener_image
  service_account_email = google_service_account.listener.email

  pubsub_topic_volume     = module.pubsub.topic_names["volume"]
  pubsub_topic_momentum   = module.pubsub.topic_names["momentum"]
  pubsub_topic_volatility = module.pubsub.topic_names["volatility"]
  pubsub_topic_sector     = module.pubsub.topic_names["sector"]

  depends_on = [
    google_project_service.apis,
    google_secret_manager_secret.finnhub_key,
    module.pubsub,
  ]
}
