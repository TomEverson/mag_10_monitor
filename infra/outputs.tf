output "listener_vm_name" {
  description = "Compute Engine instance name"
  value       = module.vm.instance_name
}

output "listener_external_ip" {
  description = "Listener VM external IP (ephemeral)"
  value       = module.vm.external_ip
}

output "pubsub_topic_names" {
  description = "Map of signal type → Pub/Sub topic name"
  value       = module.pubsub.topic_names
}

output "pubsub_subscription_ids" {
  description = "Map of signal type → subscription resource ID"
  value       = module.pubsub.subscription_ids
}

output "bq_dataset_id" {
  description = "BigQuery dataset ID"
  value       = module.bigquery.dataset_id
}

output "bq_table_ids" {
  description = "Map of table name → fully qualified BigQuery table ID"
  value       = module.bigquery.table_ids
}

output "gcs_raw_bucket" {
  description = "GCS raw event archive bucket name"
  value       = module.gcs.bucket_name
}

output "artifact_registry_repo" {
  description = "Artifact Registry repository URL"
  value       = "${var.region}-docker.pkg.dev/${var.gcp_project_id}/mag10-images"
}

output "finnhub_secret_name" {
  description = "Secret Manager secret name for the Finnhub API key"
  value       = google_secret_manager_secret.finnhub_key.secret_id
}
