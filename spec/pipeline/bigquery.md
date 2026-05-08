# Spec: BigQuery Tables

## Dataset

**Dataset name:** controlled by the `BQ_DATASET` environment variable.
Default suggested value: `signals`.

All tables are in this single dataset. The dataset is created by Terraform
(see `spec/infra/resources.md`).

---

## Partitioning & Clustering

All tables are partitioned by `timestamp` column (DAY). All dashboard queries
must include a `WHERE DATE(timestamp) = @date` (or equivalent date filter) to
use partition pruning and avoid full table scans.

Clustering is applied where noted to further reduce query costs.

---

## Table: `signals.volume_spikes`

**Populated by:** functions/volume  
**Partitioned by:** `timestamp` (DAY)  
**Clustered by:** `symbol`

| Column         | Type      | Mode     | Description |
|----------------|-----------|----------|-------------|
| `timestamp`    | TIMESTAMP | REQUIRED | Trade timestamp converted from `trade_ts` (Unix ms → TIMESTAMP) |
| `detected_at`  | TIMESTAMP | REQUIRED | When the listener emitted the signal |
| `processed_at` | TIMESTAMP | REQUIRED | When the Cloud Function processed the message |
| `symbol`       | STRING    | REQUIRED | Equity symbol (e.g. `"NVDA"`) |
| `price`        | FLOAT64   | REQUIRED | Trade price at signal time (USD) |
| `trade_volume` | FLOAT64   | REQUIRED | Volume of the triggering trade |
| `avg_volume`   | FLOAT64   | REQUIRED | Rolling average volume (excluding current trade) |
| `spike_ratio`  | FLOAT64   | REQUIRED | `trade_volume / avg_volume` |
| `window_size`  | INT64     | REQUIRED | Number of trades in the rolling window at signal time |

Notes:
- `timestamp` is derived by the Cloud Function from `trade_ts` (divide by 1000,
  convert to TIMESTAMP). It is the partition column.
- `detected_at` and `processed_at` are stored as UTC TIMESTAMP.

---

## Table: `signals.momentum_signals`

**Populated by:** functions/momentum  
**Partitioned by:** `timestamp` (DAY)  
**Clustered by:** `symbol`, `direction`

| Column          | Type      | Mode     | Description |
|-----------------|-----------|----------|-------------|
| `timestamp`     | TIMESTAMP | REQUIRED | Trade timestamp (from `trade_ts`) |
| `detected_at`   | TIMESTAMP | REQUIRED | When the listener emitted the signal |
| `processed_at`  | TIMESTAMP | REQUIRED | When the Cloud Function processed the message |
| `symbol`        | STRING    | REQUIRED | Equity symbol |
| `direction`     | STRING    | REQUIRED | `"UP"` or `"DOWN"` |
| `current_price` | FLOAT64   | REQUIRED | Price of the triggering trade |
| `anchor_price`  | FLOAT64   | REQUIRED | Oldest price in the rolling window |
| `pct_change`    | FLOAT64   | REQUIRED | Percentage change (negative for DOWN) |
| `window_size`   | INT64     | REQUIRED | Number of trades in the rolling window at signal time |

Notes:
- `pct_change` is stored with the sign intact (negative = DOWN, positive = UP).
  Dashboard queries can derive the direction from sign if needed.

---

## Table: `signals.volatility_spikes`

**Populated by:** functions/volatility  
**Partitioned by:** `timestamp` (DAY)  
**Clustered by:** `symbol`

| Column         | Type      | Mode     | Description |
|----------------|-----------|----------|-------------|
| `timestamp`    | TIMESTAMP | REQUIRED | Trade timestamp (from `trade_ts`) |
| `detected_at`  | TIMESTAMP | REQUIRED | When the listener emitted the signal |
| `processed_at` | TIMESTAMP | REQUIRED | When the Cloud Function processed the message |
| `symbol`       | STRING    | REQUIRED | Equity symbol |
| `price`        | FLOAT64   | REQUIRED | Price of the triggering trade |
| `mean_price`   | FLOAT64   | REQUIRED | Mean price across the rolling window |
| `std_dev`      | FLOAT64   | REQUIRED | Population std dev of window prices |
| `z_score`      | FLOAT64   | REQUIRED | `abs(price - mean_price) / std_dev` |
| `window_size`  | INT64     | REQUIRED | Number of trades in the rolling window at signal time |

---

## Table: `signals.sector_snapshots`

**Populated by:** functions/sector  
**Partitioned by:** `snapshot_ts` (DAY)  
**Clustered by:** `symbol`

One row per symbol per snapshot. A single Pub/Sub message (10 symbols, 1 snapshot)
produces 10 rows.

| Column          | Type      | Mode     | Description |
|-----------------|-----------|----------|-------------|
| `snapshot_ts`   | TIMESTAMP | REQUIRED | When the snapshot was taken (partition column) |
| `processed_at`  | TIMESTAMP | REQUIRED | When the Cloud Function processed the message |
| `symbol`        | STRING    | REQUIRED | Equity symbol |
| `last_price`    | FLOAT64   | NULLABLE | Most recent trade price; NULL if no trades received |
| `open_price`    | FLOAT64   | NULLABLE | First trade price of the session; NULL if no trades received |
| `pct_change`    | FLOAT64   | NULLABLE | Session price change %; NULL if price unavailable |
| `trade_count`   | INT64     | REQUIRED | Trades received this session for this symbol |
| `total_volume`  | FLOAT64   | REQUIRED | Cumulative session volume for this symbol |
| `last_trade_ts` | TIMESTAMP | NULLABLE | Timestamp of last trade; NULL if no trades received |
| `is_stale`      | BOOL      | REQUIRED | True if no trade received in last `SECTOR_STALE_SECS` seconds |

Notes:
- `snapshot_ts` is parsed from the `snapshot_ts` field in the Pub/Sub message
  (ISO 8601 → TIMESTAMP). It is the partition column.
- `last_trade_ts` is derived from the per-symbol `last_trade_ts` field (Unix ms
  → TIMESTAMP), or NULL if the field is null.

---

## Timestamp Handling (all tables)

| Source field     | BigQuery column | Conversion |
|------------------|-----------------|------------|
| `trade_ts` (int, Unix ms) | `timestamp` | `TIMESTAMP_MILLIS(trade_ts)` |
| `detected_at` (ISO 8601 string) | `detected_at` | Parse via `datetime.fromisoformat()`, store as UTC TIMESTAMP |
| `snapshot_ts` (ISO 8601 string) | `snapshot_ts` | Same as above |
| `last_trade_ts` (int, Unix ms, or null) | `last_trade_ts` | `TIMESTAMP_MILLIS(last_trade_ts)` or NULL |

All timestamps are stored in UTC. No timezone conversion is performed.

---

## BigQuery Streaming Insert Limits

- Maximum row size: 1 MB (all rows are well under 1 KB).
- Maximum rows per request: 50,000 (functions insert 1 row for signals, 10 for
  sector — well within limits).
- Streaming inserts are billed per MB inserted — keep payloads lean.
- Inserted rows are available for querying within a few seconds.
- Rows inserted via streaming cannot be deleted or updated for approximately
  90 minutes; the dashboard is read-only so this is not a concern.
