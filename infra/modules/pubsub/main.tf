resource "google_pubsub_topic" "raw_trades" {
  name                       = "mag10-raw-trades"
  message_retention_duration = "604800s" # 7 days
}

resource "google_pubsub_topic" "processed_signals" {
  name                       = "mag10-processed-signals"
  message_retention_duration = "604800s"
}

# ── Raw trades subscriptions ──────────────────────────────────────────────────

# Bronze: Pub/Sub Cloud Storage subscription — writes one file per message
resource "google_pubsub_subscription" "bronze" {
  name  = "mag10-raw-trades-bronze-sub"
  topic = google_pubsub_topic.raw_trades.name

  cloud_storage_config {
    bucket          = var.gcs_bucket
    filename_prefix = "bronze/"
    filename_suffix = ".json"
    max_duration    = "60s"
  }

  message_retention_duration = "604800s"
  ack_deadline_seconds       = 60

  depends_on = [var.gcs_bucket_resource]
}

# Detection VM: pull subscription
resource "google_pubsub_subscription" "detection" {
  name  = "mag10-raw-trades-detection-sub"
  topic = google_pubsub_topic.raw_trades.name

  ack_deadline_seconds       = 60
  message_retention_duration = "604800s"

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }
}

# ── Processed signals subscription ───────────────────────────────────────────

# CF archive: push subscription
resource "google_pubsub_subscription" "archive" {
  name  = "mag10-processed-signals-sub"
  topic = google_pubsub_topic.processed_signals.name

  ack_deadline_seconds       = 60
  message_retention_duration = "604800s"

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }

  dynamic "push_config" {
    for_each = var.archive_function_url != "" ? [1] : []
    content {
      push_endpoint = var.archive_function_url
      oidc_token {
        service_account_email = var.functions_sa_email
      }
    }
  }
}
