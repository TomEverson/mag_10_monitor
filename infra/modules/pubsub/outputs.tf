output "topic_ids" {
  description = "Map of topic key → full topic resource ID"
  value       = { for k, t in google_pubsub_topic.topics : k => t.id }
}

output "topic_names" {
  description = "Map of topic key → topic name (short)"
  value       = { for k, t in google_pubsub_topic.topics : k => t.name }
}

output "subscription_ids" {
  description = "Map of topic key → subscription resource ID"
  value       = { for k, s in google_pubsub_subscription.subscriptions : k => s.id }
}
