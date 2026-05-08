# Spec: Momentum Signal Detector

## Purpose

Detect when a symbol is exhibiting a sustained directional price move — i.e.
the price has shifted meaningfully from where it was N trades ago. This catches
trending moves rather than single-trade noise.

---

## Algorithm

Each symbol maintains an independent rolling window of recent trade prices.

```
rolling_window[symbol] = deque of last MOMENTUM_WINDOW_SIZE trade prices
```

On each incoming trade for a symbol:

1. Append `trade.p` to `rolling_window[symbol]`.
2. If `len(rolling_window[symbol]) < MOMENTUM_MIN_TRADES`, skip signal check.
3. Let `anchor_price = rolling_window[symbol][0]` — the oldest price in the window.
4. Let `current_price = trade.p`.
5. Compute `pct_change = (current_price - anchor_price) / anchor_price * 100`.
6. If `pct_change >= +MOMENTUM_THRESHOLD_PCT`, emit a signal with `direction = "UP"`.
7. If `pct_change <= -MOMENTUM_THRESHOLD_PCT`, emit a signal with `direction = "DOWN"`.

The anchor is the oldest retained price, so the threshold measures the full
move across the window — not tick-to-tick noise.

---

## Configuration

All values live in `listener/config.py`.

| Constant                    | Default | Description |
|-----------------------------|---------|-------------|
| `MOMENTUM_WINDOW_SIZE`      | 15      | Max trades retained in the rolling window per symbol |
| `MOMENTUM_MIN_TRADES`       | 8       | Minimum trades in window before any signal can fire |
| `MOMENTUM_THRESHOLD_PCT`    | 0.5     | Percentage price change from window anchor required to fire |
| `MOMENTUM_COOLDOWN_SECS`    | 60      | Seconds before another momentum signal can fire for the same symbol |

---

## Signal Payload

| Field           | Type    | Description |
|-----------------|---------|-------------|
| `signal_type`   | string  | Always `"momentum_signal"` |
| `symbol`        | string  | The equity symbol |
| `direction`     | string  | `"UP"` or `"DOWN"` |
| `current_price` | float   | Price of the triggering trade |
| `anchor_price`  | float   | Oldest price in the rolling window |
| `pct_change`    | float   | `(current_price - anchor_price) / anchor_price * 100`, rounded to 3 dp |
| `window_size`   | integer | Number of trades in the window at signal time |
| `trade_ts`      | integer | Trade timestamp from Finnhub (Unix milliseconds) |
| `detected_at`   | string  | ISO 8601 UTC timestamp when the signal was emitted |

### Example

```json
{
  "signal_type": "momentum_signal",
  "symbol": "TSLA",
  "direction": "DOWN",
  "current_price": 162.80,
  "anchor_price": 164.10,
  "pct_change": -0.792,
  "window_size": 15,
  "trade_ts": 1715172188000,
  "detected_at": "2024-05-08T14:09:48.017Z"
}
```

---

## Cooldown

After a signal fires for a symbol, no further momentum signal fires for that
symbol for `MOMENTUM_COOLDOWN_SECS` seconds. The rolling window continues
accumulating trades during the cooldown.

The cooldown does **not** reset direction independently — if an UP signal fires
and the price then reverses, a DOWN signal can still fire once the cooldown
expires.

---

## Edge Cases

- If the anchor price is 0, skip the signal check.
- A signal fires on the first trade that crosses the threshold; subsequent
  trades in the same direction during the cooldown window do not re-fire.
- The rolling window is reset to empty on WebSocket reconnect.
