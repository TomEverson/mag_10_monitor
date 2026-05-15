# Spec: Overview

## Purpose

mag10-monitor is a real-time market intelligence pipeline. It ingests live trade
data for 10 high-interest equities (MAG 7 + AMD, AVGO, PLTR), runs four signal
detectors against the trade stream, and surfaces detected signals on a Streamlit
dashboard backed by BigQuery.

The system is intentionally minimal — it runs on two e2-micro VMs, two Cloud
Functions, and one Cloud Run service. It does not trade, place orders, or consume
any paid market data feed beyond the Finnhub free tier.

---

## Tracked Symbols

| Symbol | Name | Group |
|---|---|---|
| AAPL | Apple | MAG 7 |
| MSFT | Microsoft | MAG 7 |
| NVDA | NVIDIA | MAG 7 |
| GOOGL | Alphabet | MAG 7 |
| AMZN | Amazon | MAG 7 |
| META | Meta Platforms | MAG 7 |
| TSLA | Tesla | MAG 7 |
| AMD | Advanced Micro | Extended |
| AVGO | Broadcom | Extended |
| PLTR | Palantir | Extended |

All 10 symbols are subscribed in a single Finnhub WebSocket session.

---

## Signal Types

| Signal | What it detects | Cadence |
|---|---|---|
| `volume_spike` | Unusual trade volume burst for a symbol | On threshold breach |
| `momentum_signal` | Sustained directional price movement | On threshold breach |
| `volatility_spike` | Abnormal price variance within a window | On threshold breach |
| `sector_snapshot` | Periodic aggregate state across all symbols | Every 60 seconds |

---

## Data Layers

| Layer | Storage | Contents |
|---|---|---|
| **Bronze** | GCS (`bronze/`) | Raw validated trades — immutable, used for warm-start |
| **Silver** | GCS (`silver/`) + BigQuery | Detected signals — GCS for archive, BQ for querying |
| **Gold** | BigQuery | Served directly to the Streamlit dashboard |

---

## Data Flow

```
Finnhub WebSocket
      │
      ▼
WebSocket VM (ingest only)
  validates raw trades
  publishes to Pub/Sub
      │
      ▼
Pub/Sub: mag10-raw-trades
  ├──► Cloud Storage subscription → GCS bronze/  (Bronze)
  └──► Pull subscription → Detection VM
                             4 stateful detectors
                             warm-starts from GCS bronze/ on restart
                                   │
                                   ▼
                          Pub/Sub: mag10-processed-signals
                                   │
                                   ▼
                            CF archive
                            routes by signal_type
                            ├──► silver/volume/
                            ├──► silver/momentum/
                            ├──► silver/volatility/
                            └──► silver/sector/     (Silver GCS)
                                   │
                              GCS trigger
                                   │
                                   ▼
                            CF gcs-to-bq
                            routes by GCS path
                            ├──► BQ volume_spikes
                            ├──► BQ momentum_signals
                            ├──► BQ volatility_spikes
                            └──► BQ sector_snapshots (Silver BQ)
                                   │
                                   ▼
                          Streamlit Dashboard (Cloud Run)
```

---

## Spec Map

| File | What it covers |
|---|---|
| `spec/data-sources.md` | Finnhub WebSocket connection, message format, reconnection |
| `spec/detectors/volume.md` | Volume spike detector algorithm and thresholds |
| `spec/detectors/momentum.md` | Momentum signal detector algorithm and thresholds |
| `spec/detectors/volatility.md` | Volatility spike detector algorithm and thresholds |
| `spec/detectors/sector.md` | Sector snapshot aggregation and cadence |
| `spec/pipeline/listener.md` | WebSocket VM and Detection VM responsibilities |
| `spec/pipeline/bronze.md` | Bronze layer — GCS raw trade archive and warm-start |
| `spec/pipeline/pubsub.md` | Pub/Sub topics, subscriptions, and message schemas |
| `spec/pipeline/functions.md` | CF archive and CF gcs-to-bq responsibilities |
| `spec/pipeline/bigquery.md` | BigQuery table schemas (full column definitions) |
| `spec/dashboard/boards.md` | Streamlit dashboard tab layout and backing queries |
| `spec/infra/resources.md` | GCP resource inventory and Terraform module map |

---

## Non-Goals

- No trading or order placement of any kind
- No options, futures, or non-equity instruments
- No pre-market or after-hours signal detection
- No alert routing (email, SMS, Slack) — dashboard is the only output surface
- No historical backfill — pipeline is live-forward only
