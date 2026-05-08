# Spec: Volatility Spike Detector

## Purpose

Detect when a symbol's price is swinging abnormally within a short window —
i.e. high intra-window variance, not just a single large move. This catches
choppy, erratic behaviour that momentum alone would miss.

---

## Algorithm

Each symbol maintains an independent rolling window of recent trade prices.

```
rolling_window[symbol] = deque of last VOLATILITY_WINDOW_SIZE trade prices
```

On each incoming trade for a symbol:

1. Append `trade.p` to `rolling_window[symbol]`.
2. If `len(rolling_window[symbol]) < VOLATILITY_MIN_TRADES`, skip signal check.
3. Compute `mean_price = mean(rolling_window[symbol])`.
4. Compute `std_dev = population standard deviation of rolling_window[symbol]`.
5. If `std_dev == 0`, skip (all prices identical — no volatility).
6. Compute `z_score = abs(trade.p - mean_price) / std_dev`.
7. If `z_score >= VOLATILITY_Z_THRESHOLD`, emit a signal.

The z-score measures how many standard deviations the current trade price is
from the window mean. A z-score ≥ 2.0 means the current price is an outlier
relative to recent activity.

---

## Configuration

All values live in `listener/config.py`.

| Constant                      | Default | Description |
|-------------------------------|---------|-------------|
| `VOLATILITY_WINDOW_SIZE`      | 20      | Max trades retained in the rolling window per symbol |
| `VOLATILITY_MIN_TRADES`       | 10      | Minimum trades in window before any signal can fire |
| `VOLATILITY_Z_THRESHOLD`      | 2.0     | Z-score threshold for a spike |
| `VOLATILITY_COOLDOWN_SECS`    | 45      | Seconds before another volatility spike can fire for the same symbol |

---

## Signal Payload

| Field         | Type    | Description |
|---------------|---------|-------------|
| `signal_type` | string  | Always `"volatility_spike"` |
| `symbol`      | string  | The equity symbol |
| `price`       | float   | Price of the triggering trade |
| `mean_price`  | float   | Mean price across the window (rounded to 4 dp) |
| `std_dev`     | float   | Population standard deviation of prices in window (rounded to 4 dp) |
| `z_score`     | float   | `abs(price - mean_price) / std_dev` (rounded to 3 dp) |
| `window_size` | integer | Number of trades in the window at signal time |
| `trade_ts`    | integer | Trade timestamp from Finnhub (Unix milliseconds) |
| `detected_at` | string  | ISO 8601 UTC timestamp when the signal was emitted |

### Example

```json
{
  "signal_type": "volatility_spike",
  "symbol": "AMD",
  "price": 158.72,
  "mean_price": 155.4180,
  "std_dev": 1.6240,
  "z_score": 2.041,
  "window_size": 20,
  "trade_ts": 1715172301000,
  "detected_at": "2024-05-08T14:11:41.889Z"
}
```

---

## Cooldown

After a signal fires for a symbol, no further volatility spike fires for that
symbol for `VOLATILITY_COOLDOWN_SECS` seconds. The rolling window continues
accumulating trades during the cooldown.

---

## Edge Cases

- If `std_dev == 0` (all prices in the window are identical), the z-score is
  undefined — skip the check.
- The rolling window is reset to empty on WebSocket reconnect.
- Population standard deviation is used (divides by N, not N-1) because the
  window represents the full recent population of interest, not a sample.
