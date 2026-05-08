variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "dataset_id" {
  description = "BigQuery dataset ID"
  type        = string
  default     = "signals"
}

variable "location" {
  description = "BigQuery dataset location"
  type        = string
  default     = "US"
}
