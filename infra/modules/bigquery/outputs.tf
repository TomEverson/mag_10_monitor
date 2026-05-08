output "dataset_id" {
  value = google_bigquery_dataset.signals.dataset_id
}

output "table_ids" {
  description = "Map of table name → fully qualified table ID"
  value = {
    volume_spikes     = google_bigquery_table.volume_spikes.id
    momentum_signals  = google_bigquery_table.momentum_signals.id
    volatility_spikes = google_bigquery_table.volatility_spikes.id
    sector_snapshots  = google_bigquery_table.sector_snapshots.id
  }
}
