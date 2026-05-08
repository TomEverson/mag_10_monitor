locals {
  topics = {
    volume     = "mag10-volume-spike"
    momentum   = "mag10-momentum-signal"
    volatility = "mag10-volatility-spike"
    sector     = "mag10-sector-snapshot"
  }

  # Map each topic key to its optional function URL variable
  function_urls = {
    volume     = var.volume_function_url
    momentum   = var.momentum_function_url
    volatility = var.volatility_function_url
    sector     = var.sector_function_url
  }
}

resource "google_pubsub_topic" "topics" {
  for_each = local.topics
  name     = each.value

  message_retention_duration = "604800s" # 7 days
}

resource "google_pubsub_subscription" "subscriptions" {
  for_each = local.topics
  name     = "${each.value}-sub"
  topic    = google_pubsub_topic.topics[each.key].name

  ack_deadline_seconds       = 60
  message_retention_duration = "604800s"

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }

  # Push delivery is configured once the Cloud Function URL is known.
  # Leave function URL variables empty for the initial apply (pull mode).
  # After deploying functions, set the URLs and run terraform apply again.
  dynamic "push_config" {
    for_each = local.function_urls[each.key] != "" ? [1] : []
    content {
      push_endpoint = local.function_urls[each.key]
      oidc_token {
        service_account_email = var.functions_sa_email
      }
    }
  }
}
