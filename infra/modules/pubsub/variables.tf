variable "functions_sa_email" {
  description = "Service account email used for OIDC tokens on push subscriptions"
  type        = string
}

# Function URLs — optional. When empty the subscription is pull (pre-deploy).
# Set these after Cloud Functions are deployed and run terraform apply again.
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
