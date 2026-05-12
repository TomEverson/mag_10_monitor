-- Momentum Board
-- All momentum signal events for the selected date, newest first.
-- Partition column: window_end_ts (DAY), clustered by symbol and direction
SELECT
  window_end_ts,
  window_start_ts,
  symbol,
  direction,
  oldest_open,
  latest_close,
  pct_change,
  candles_in_direction,
  total_candles,
  detected_at
FROM `{project}.signals.momentum_signals`
WHERE DATE(window_end_ts) = @date
ORDER BY window_end_ts DESC
