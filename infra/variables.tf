variable "gcp_project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "Default GCP region"
  type        = string
  default     = "asia-southeast1"
}

variable "zone" {
  description = "Compute zone for VMs"
  type        = string
  default     = "asia-southeast1-b"
}

variable "env" {
  description = "Environment suffix applied to resource names (prod | dev)"
  type        = string
  default     = "prod"
}

variable "bq_dataset" {
  description = "BigQuery dataset ID"
  type        = string
  default     = "signals"
}

variable "websocket_image" {
  description = "Full Artifact Registry Docker image URI for the WebSocket ingest service"
  type        = string
}

variable "detection_image" {
  description = "Full Artifact Registry Docker image URI for the signal detection service"
  type        = string
}

variable "dashboard_image" {
  description = "Full Artifact Registry Docker image URI for the dashboard"
  type        = string
}

# Leave empty on first apply (subscription uses pull mode).
# Set after deploying the archive Cloud Function, then run terraform apply again
# to switch the Pub/Sub subscription from pull to push.
variable "archive_function_url" {
  description = "HTTPS URL of the mag10-archive Cloud Function"
  type        = string
  default     = ""
}
