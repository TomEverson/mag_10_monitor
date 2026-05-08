# Spec: Overview

## Purpose

mag10-monitor is a real-time market intelligence pipeline. It ingests live trade
data for 10 high-interest equities (MAG 7 + AMD, AVGO, PLTR), runs four signal
detectors against the trade stream, and surfaces detected signals on a Looker
Studio dashboard backed by BigQuery.

The system is intentionally minimal — it runs on a single e2-micro VM and four
lightweight Cloud Functions. It does not trade, place orders, or consume any
paid market data feed beyond the Finnhub free tier.

---

## Tracked Symbols

| Symbol | Name              | Group    |
|--------|-------------------|----------|
| AAPL   | Apple             | MAG 7    |
| MSFT   | Microsoft         | MAG 7    |
| NVDA   | NVIDIA            | MAG 7    |
| GOOGL  | Alphabet          | MAG 7    |
| AMZN   | Amazon            | MAG 7    |
| META   | Meta Platforms    | MAG 7    |
| TSLA   | Tesla             | MAG 7    |
| AMD    | Advanced Micro    | Extended |
| AVGO   | Broadcom          | Extended |
| PLTR   | Palantir          | Extended |

All 10 symbols are subscribed in a single Finnhub WebSocket session.

---

## Signal Types

| Signal           | What it detects                              | Cadence           |
|------------------|----------------------------------------------|-------------------|
| volume-spike     | Unusual trade volume burst for a symbol      | On threshold breach |
| momentum-signal  | Sustained directional price movement         | On threshold breach |
| volatility-spike | Abnormal price variance within a window      | On threshold breach |
| sector-snapshot  | Periodic aggregate state across all symbols  | Every 60 seconds  |

---

## Data Flow

```
Finnhub WebSocket
      │  trade messages (JSON)
      ▼
listener (e2-micro VM)
      │  runs 4 detectors in-process
      │  detectors hold rolling windows in memory
      │
      ├──► Pub/Sub: mag10-volume-spike       (on signal)
      ├──► Pub/Sub: mag10-momentum-signal    (on signal)
      ├──► Pub/Sub: mag10-volatility-spike   (on signal)
      └──► Pub/Sub: mag10-sector-snapshot    (every 60s)
                │
                ▼
         Cloud Functions (one per topic)
           │  enriches payload
           │  archives raw event to GCS
           │  writes to BigQuery via streaming insert
                │
                ▼
           BigQuery (dataset: signals)
                │
                ▼
           Looker Studio Dashboard
```

---

## Spec Map

| File | What it covers |
|------|----------------|
| `spec/data-sources.md` | Finnhub WebSocket connection, message format, reconnection |
| `spec/detectors/volume.md` | Volume spike detector algorithm and thresholds |
| `spec/detectors/momentum.md` | Momentum signal detector algorithm and thresholds |
| `spec/detectors/volatility.md` | Volatility spike detector algorithm and thresholds |
| `spec/detectors/sector.md` | Sector snapshot aggregation and cadence |
| `spec/pipeline/listener.md` | Listener process: WebSocket lifecycle, detector orchestration |
| `spec/pipeline/pubsub.md` | Pub/Sub topic names and full message schemas |
| `spec/pipeline/functions.md` | Cloud Function responsibilities, error handling, idempotency |
| `spec/pipeline/bigquery.md` | BigQuery table schemas (full column definitions) |
| `spec/dashboard/boards.md` | Looker Studio board layout and backing queries |
| `spec/infra/resources.md` | GCP resource inventory and Terraform module map |

---

## Non-Goals

- No trading or order placement of any kind
- No options, futures, or non-equity instruments
- No pre-market or after-hours signal detection (listener handles the no-trade window gracefully but does not generate signals outside market hours)
- No alert routing (email, SMS, Slack) — dashboard is the only output surface
- No historical backfill — pipeline is live-forward only
