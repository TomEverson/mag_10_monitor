# Spec: Looker Studio Dashboard

## Overview

The dashboard has four boards, each backed by a BigQuery query. All boards
share a date-range control and a symbol multi-select filter. Boards display
today's data by default.

All backing queries are stored in `dashboard/queries/`. Each `.sql` file uses
`@date` as a parameterised date filter for partition pruning.

---

## Board 1: Sector Heat Map

**Query file:** `dashboard/queries/sector_heatmap.sql`  
**Chart type:** Table or scorecard grid (10 cells, one per symbol)  
**Refresh:** Every 5 minutes (Looker Studio auto-refresh)

### What it shows

A colour-coded grid of all 10 symbols showing their latest session performance:

| Column shown    | Source field     | Format |
|-----------------|------------------|--------|
| Symbol          | `symbol`         | Text   |
| Last Price      | `last_price`     | USD 2dp |
| Session Change  | `pct_change`     | %, coloured green if > 0, red if < 0 |
| Session Volume  | `total_volume`   | Number with comma separator |
| Stale indicator | `is_stale`       | ⚠ icon if true |

### Query logic

Select the most recent snapshot row per symbol for the target date:

```sql
SELECT
  symbol,
  last_price,
  open_price,
  pct_change,
  total_volume,
  is_stale,
  snapshot_ts
FROM (
  SELECT *,
    ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY snapshot_ts DESC) AS rn
  FROM `{project}.signals.sector_snapshots`
  WHERE DATE(snapshot_ts) = @date
)
WHERE rn = 1
ORDER BY symbol
```

---

## Board 2: Volume Spotter

**Query file:** `dashboard/queries/volume_spotter.sql`  
**Chart type:** Time series line chart + table  
**Refresh:** Every 5 minutes

### What it shows

Volume spike events over the day, with spike ratio on the y-axis. Allows
identification of which symbols had the most intense volume bursts and when.

| Column shown   | Source field   | Format |
|----------------|----------------|--------|
| Time           | `timestamp`    | HH:MM:SS |
| Symbol         | `symbol`       | Text (filterable) |
| Trade Price    | `price`        | USD 2dp |
| Trade Volume   | `trade_volume` | Number |
| Avg Volume     | `avg_volume`   | Number |
| Spike Ratio    | `spike_ratio`  | Number 2dp, coloured by intensity |

### Query logic

```sql
SELECT
  timestamp,
  symbol,
  price,
  trade_volume,
  avg_volume,
  spike_ratio,
  window_size
FROM `{project}.signals.volume_spikes`
WHERE DATE(timestamp) = @date
ORDER BY timestamp DESC
```

---

## Board 3: Volatility Spike Detector

**Query file:** `dashboard/queries/volatility_spike.sql`  
**Chart type:** Scatter plot (x = time, y = z_score) + table  
**Refresh:** Every 5 minutes

### What it shows

Volatility spike events over the day. Z-score on the y-axis visualises the
severity of each spike relative to the symbol's recent price distribution.

| Column shown  | Source field  | Format |
|---------------|---------------|--------|
| Time          | `timestamp`   | HH:MM:SS |
| Symbol        | `symbol`      | Text (filterable) |
| Trade Price   | `price`       | USD 2dp |
| Mean Price    | `mean_price`  | USD 4dp |
| Std Dev       | `std_dev`     | Number 4dp |
| Z-Score       | `z_score`     | Number 3dp |

### Query logic

```sql
SELECT
  timestamp,
  symbol,
  price,
  mean_price,
  std_dev,
  z_score,
  window_size
FROM `{project}.signals.volatility_spikes`
WHERE DATE(timestamp) = @date
ORDER BY timestamp DESC
```

---

## Board 4: Momentum Board

**Query file:** `dashboard/queries/momentum_board.sql`  
**Chart type:** Bar chart (counts by symbol and direction) + table  
**Refresh:** Every 5 minutes

### What it shows

Momentum signal events, separated by direction (UP/DOWN). Allows identification
of which symbols are exhibiting sustained directional moves.

| Column shown   | Source field    | Format |
|----------------|-----------------|--------|
| Time           | `timestamp`     | HH:MM:SS |
| Symbol         | `symbol`        | Text (filterable) |
| Direction      | `direction`     | UP (green) / DOWN (red) |
| Price          | `current_price` | USD 2dp |
| Anchor Price   | `anchor_price`  | USD 2dp |
| % Change       | `pct_change`    | %, signed |

The bar chart aggregates signal count by symbol and direction for the selected
date, giving a quick sense of bias.

### Query logic

```sql
SELECT
  timestamp,
  symbol,
  direction,
  current_price,
  anchor_price,
  pct_change,
  window_size
FROM `{project}.signals.momentum_signals`
WHERE DATE(timestamp) = @date
ORDER BY timestamp DESC
```

---

## Shared Controls

| Control        | Applies to | Default |
|----------------|------------|---------|
| Date range     | All boards | Today   |
| Symbol filter  | All boards | All 10  |

---

## Notes

- Dashboard queries use `@date` (a Looker Studio date parameter) — this must
  be a `DATE` type filter matching the partition column.
- No joins across tables are required; each board reads from exactly one table.
- The `{project}` placeholder in queries must be replaced with the actual GCP
  project ID when the queries are registered in Looker Studio.
