-- Volatility Spike Detector
-- All volatility spike events for the selected date, newest first.
-- Partition column: timestamp (DAY), clustered by symbol
SELECT
  timestamp,
  symbol,
  price,
  mean_price,
  std_dev,
  z_score,
  window_trade_count,
  window_span_secs,
  detected_at
FROM `{project}.signals.volatility_spikes`
WHERE DATE(timestamp) = @date
ORDER BY timestamp DESC
