-- Sector Heat Map
-- One row per symbol — the most recent snapshot for the selected date.
-- Partition column: snapshot_ts (DAY)
SELECT
  symbol,
  last_price,
  open_price,
  pct_change,
  trade_count,
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
