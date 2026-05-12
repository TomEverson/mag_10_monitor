-- Volume Spotter
-- All volume spike events for the selected date, newest first.
-- Partition column: timestamp (DAY), clustered by symbol
SELECT
  timestamp,
  symbol,
  price,
  trade_volume,
  avg_volume,
  spike_ratio,
  window_trade_count,
  window_span_secs,
  detected_at
FROM `{project}.signals.volume_spikes`
WHERE DATE(timestamp) = @date
ORDER BY timestamp DESC
