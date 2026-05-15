 Finnhub WebSocket
        ↓
  WebSocket VM (ingest only)
        ↓
  Pub/Sub: raw trades
    ├→ Bronze subscription → CF → GCS (Bronze - raw trades)
    └→ Detection subscription → Detection VM
                                        ↓
                               Pub/Sub: processed signals
                                 ├→ sub (signal_type = volume_spike)     → GCS (Silver) → CF volume     → BQ volume_spikes
                                 ├→ sub (signal_type = momentum_signal)  → GCS (Silver) → CF momentum   → BQ momentum_signals
                                 ├→ sub (signal_type = volatility_spike) → GCS (Silver) → CF volatility → BQ volatility_spikes
                                 └→ sub (signal_type = sector_snapshot)  → GCS (Silver) → CF sector     → BQ sector_snapshots
                                                                                                  ↓
                                                                                       Streamlit Dashboard (Cloud Run)
