variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region (used to configure Artifact Registry Docker auth)"
  type        = string
}

variable "zone" {
  description = "Compute zone for the VM"
  type        = string
  default     = "asia-southeast1-b"
}

variable "env" {
  description = "Environment suffix (prod | dev)"
  type        = string
  default     = "prod"
}

variable "image" {
  description = "Full Artifact Registry Docker image URI for the websocket service"
  type        = string
}

variable "service_account_email" {
  description = "Service account email for the VM"
  type        = string
}

variable "finnhub_secret_name" {
  description = "Secret Manager secret name for the Finnhub API key"
  type        = string
  default     = "mag10-finnhub-key"
}

variable "pubsub_topic_raw_trades" {
  description = "Pub/Sub topic name for raw trades"
  type        = string
  default     = "mag10-raw-trades"
}
