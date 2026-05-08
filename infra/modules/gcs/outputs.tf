output "bucket_name" {
  value = google_storage_bucket.raw.name
}

output "bucket_url" {
  value = google_storage_bucket.raw.url
}
