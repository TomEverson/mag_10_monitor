variable "gcp_project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "Default GCP region"
  type        = string
  default     = "us-central1"
}

variable "zone" {
  description = "Compute zone for the listener VM"
  type        = string
  default     = "us-central1-a"
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

variable "listener_image" {
  description = "Full Artifact Registry Docker image URI for the listener (e.g. us-central1-docker.pkg.dev/project/mag10-images/listener:latest)"
  type        = string
}

# Cloud Function URLs — leave empty on first apply (subscriptions use pull).
# Set after functions are deployed and run terraform apply again to switch to push.
variable "volume_function_url" {
  description = "Cloud Function URL for the volume spike handler"
  type        = string
  default     = ""
}

variable "momentum_function_url" {
  description = "Cloud Function URL for the momentum signal handler"
  type        = string
  default     = ""
}

variable "volatility_function_url" {
  description = "Cloud Function URL for the volatility spike handler"
  type        = string
  default     = ""
}

variable "sector_function_url" {
  description = "Cloud Function URL for the sector snapshot handler"
  type        = string
  default     = ""
}
