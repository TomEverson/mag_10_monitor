variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "zone" {
  description = "Compute zone for the listener VM"
  type        = string
  default     = "us-central1-a"
}

variable "env" {
  description = "Environment suffix (prod | dev)"
  type        = string
  default     = "prod"
}

variable "listener_image" {
  description = "Full Artifact Registry Docker image URI for the listener"
  type        = string
}

variable "service_account_email" {
  description = "Service account email for the listener VM"
  type        = string
}

variable "finnhub_secret_name" {
  description = "Secret Manager secret name for the Finnhub API key"
  type        = string
  default     = "mag10-finnhub-key"
}

variable "pubsub_topic_volume" {
  type    = string
  default = "mag10-volume-spike"
}

variable "pubsub_topic_momentum" {
  type    = string
  default = "mag10-momentum-signal"
}

variable "pubsub_topic_volatility" {
  type    = string
  default = "mag10-volatility-spike"
}

variable "pubsub_topic_sector" {
  type    = string
  default = "mag10-sector-snapshot"
}
