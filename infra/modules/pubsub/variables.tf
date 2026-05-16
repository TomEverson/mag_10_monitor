variable "functions_sa_email" {
  description = "Service account email used for OIDC tokens on push subscriptions"
  type        = string
}

variable "gcs_bucket" {
  description = "GCS bucket name for the Bronze Cloud Storage subscription"
  type        = string
}

variable "gcs_bucket_resource" {
  description = "GCS bucket resource — used to ensure the bucket exists before creating the subscription"
  type        = any
}

variable "archive_function_url" {
  description = "CF archive URL — leave empty on first apply (pull mode), set after deploying the function"
  type        = string
  default     = ""
}
