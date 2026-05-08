resource "google_bigquery_dataset" "signals" {
  dataset_id  = var.dataset_id
  location    = var.location
  description = "MAG10 market signal tables"

  delete_contents_on_destroy = false
}

resource "google_bigquery_table" "volume_spikes" {
  dataset_id          = google_bigquery_dataset.signals.dataset_id
  table_id            = "volume_spikes"
  schema              = file("${path.module}/schemas/volume_spikes.json")
  deletion_protection = true

  time_partitioning {
    type  = "DAY"
    field = "timestamp"
  }

  clustering = ["symbol"]
}

resource "google_bigquery_table" "momentum_signals" {
  dataset_id          = google_bigquery_dataset.signals.dataset_id
  table_id            = "momentum_signals"
  schema              = file("${path.module}/schemas/momentum_signals.json")
  deletion_protection = true

  time_partitioning {
    type  = "DAY"
    field = "window_end_ts"
  }

  clustering = ["symbol", "direction"]
}

resource "google_bigquery_table" "volatility_spikes" {
  dataset_id          = google_bigquery_dataset.signals.dataset_id
  table_id            = "volatility_spikes"
  schema              = file("${path.module}/schemas/volatility_spikes.json")
  deletion_protection = true

  time_partitioning {
    type  = "DAY"
    field = "timestamp"
  }

  clustering = ["symbol"]
}

resource "google_bigquery_table" "sector_snapshots" {
  dataset_id          = google_bigquery_dataset.signals.dataset_id
  table_id            = "sector_snapshots"
  schema              = file("${path.module}/schemas/sector_snapshots.json")
  deletion_protection = true

  time_partitioning {
    type  = "DAY"
    field = "snapshot_ts"
  }

  clustering = ["symbol"]
}
