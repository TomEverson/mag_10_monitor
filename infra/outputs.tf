output "websocket_vm_name" {
  description = "WebSocket ingest VM name"
  value       = module.vm.instance_name
}

output "websocket_external_ip" {
  description = "WebSocket VM external IP (ephemeral)"
  value       = module.vm.external_ip
}

output "detection_vm_name" {
  description = "Signal detection VM name"
  value       = google_compute_instance.detection.name
}

output "detection_external_ip" {
  description = "Detection VM external IP (ephemeral)"
  value       = google_compute_instance.detection.network_interface[0].access_config[0].nat_ip
}

output "raw_trades_topic_name" {
  description = "Pub/Sub topic name for raw trades"
  value       = module.pubsub.raw_trades_topic_name
}

output "processed_signals_topic_name" {
  description = "Pub/Sub topic name for processed signals"
  value       = module.pubsub.processed_signals_topic_name
}

output "detection_subscription_name" {
  description = "Pub/Sub pull subscription name for the detection VM"
  value       = module.pubsub.detection_subscription_name
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
  description = "GCS bucket name (Bronze + Silver layers)"
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

output "dashboard_url" {
  description = "Cloud Run dashboard URL"
  value       = google_cloud_run_v2_service.dashboard.uri
}
