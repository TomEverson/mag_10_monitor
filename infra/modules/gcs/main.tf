resource "google_storage_bucket" "raw" {
  # Bucket names must be globally unique; project ID suffix ensures this
  name          = "mag-10-raw"
  location      = var.region
  storage_class = "STANDARD"

  uniform_bucket_level_access = true

  public_access_prevention = "enforced"

  versioning {
    enabled = false
  }

  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      age = 90 # days
    }
  }
}
