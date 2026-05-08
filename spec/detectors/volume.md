# Spec: Volume Spike Detector

## Purpose

Detect when a single trade's volume is significantly larger than the recent
baseline for that symbol, indicating unusual buying or selling activity.

---

## Algorithm

Each symbol maintains an independent rolling window of recent trade volumes.

```
rolling_window[symbol] = deque of last VOLUME_WINDOW_SIZE trade volumes
```

On each incoming trade for a symbol:

1. Append `trade.v` to `rolling_window[symbol]`.
2. If `len(rolling_window[symbol]) < VOLUME_MIN_TRADES`, skip signal check
   (insufficient baseline).
3. Compute `avg_volume = mean(rolling_window[symbol][:-1])` — the average of
   all volumes **excluding** the current trade.
4. If `avg_volume == 0`, skip signal check.
5. If `trade.v >= avg_volume * VOLUME_SPIKE_MULTIPLIER`, emit a signal.

The current trade is excluded from the average to avoid self-reinforcement.

---

## Configuration

All values live in `listener/config.py`.

| Constant                  | Default | Description |
|---------------------------|---------|-------------|
| `VOLUME_WINDOW_SIZE`      | 20      | Max trades retained in the rolling window per symbol |
| `VOLUME_MIN_TRADES`       | 5       | Minimum trades in window before any signal can fire |
| `VOLUME_SPIKE_MULTIPLIER` | 2.5     | Current trade volume must be ≥ this multiple of the window average |

---

## Signal Payload

When a spike is detected, the detector emits a dict with the following fields.
This dict is serialised to JSON and published to the `mag10-volume-spike`
Pub/Sub topic.

| Field             | Type    | Description |
|-------------------|---------|-------------|
| `signal_type`     | string  | Always `"volume_spike"` |
| `symbol`          | string  | The equity symbol (e.g. `"NVDA"`) |
| `price`           | float   | Trade price that triggered the signal |
| `trade_volume`    | float   | Volume of the triggering trade |
| `avg_volume`      | float   | Rolling average volume at the time of the signal (rounded to 2 dp) |
| `spike_ratio`     | float   | `trade_volume / avg_volume` (rounded to 2 dp) |
| `window_size`     | integer | Number of trades in the window at signal time |
| `trade_ts`        | integer | Trade timestamp from Finnhub (Unix milliseconds) |
| `detected_at`     | string  | ISO 8601 UTC timestamp when the signal was emitted by the detector |

### Example

```json
{
  "signal_type": "volume_spike",
  "symbol": "NVDA",
  "price": 875.30,
  "trade_volume": 12500,
  "avg_volume": 4200.50,
  "spike_ratio": 2.98,
  "window_size": 20,
  "trade_ts": 1715172043000,
  "detected_at": "2024-05-08T14:07:23.412Z"
}
```

---

## Cooldown

To avoid flooding Pub/Sub with repeated signals on a sustained burst, a
per-symbol cooldown applies after each signal fires:

| Constant                | Default | Description |
|-------------------------|---------|-------------|
| `VOLUME_COOLDOWN_SECS`  | 30      | Seconds before another volume spike signal can fire for the same symbol |

The cooldown timer resets each time a signal fires. Trades during the cooldown
period are still added to the rolling window.

---

## Edge Cases

- If a symbol has not yet received `VOLUME_MIN_TRADES` trades since startup or
  last reconnect, no signal fires regardless of volume.
- If all previous trades in the window have volume 0 (e.g. odd-lot conditions),
  `avg_volume` is 0 and the check is skipped.
- The rolling window is reset to empty on WebSocket reconnect.
