output "raw_trades_topic_name" {
  value = google_pubsub_topic.raw_trades.name
}

output "processed_signals_topic_name" {
  value = google_pubsub_topic.processed_signals.name
}

output "detection_subscription_name" {
  value = google_pubsub_subscription.detection.name
}
