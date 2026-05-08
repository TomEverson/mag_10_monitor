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

  depends_on = [google_project_service.apis]
}

module "vm" {
  source = "./modules/vm"

  project_id            = var.gcp_project_id
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
