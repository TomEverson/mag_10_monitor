# Spec: Pub/Sub Topics & Message Schemas

## Topics

| Topic name | Published by | Consumed by | Trigger |
|---|---|---|---|
| `mag10-raw-trades` | WebSocket VM | Bronze (Cloud Storage sub) + Detection VM (pull sub) | Every validated trade |
| `mag10-processed-signals` | Detection VM | CF archive (push sub) | Every detected signal |

All topic names are stored in environment variables. Terraform creates the
topics with these exact names.

---

## Subscriptions

### mag10-raw-trades

| Subscription ID | Type | Delivers to |
|---|---|---|
| `mag10-raw-trades-bronze-sub` | Cloud Storage | GCS `bronze/` prefix (native, no CF) |
| `mag10-raw-trades-detection-sub` | Pull | Detection VM |

The Cloud Storage subscription writes one GCS object per Pub/Sub message.
The Detection VM uses a streaming pull subscription — it is not push-triggered.

### mag10-processed-signals

| Subscription ID | Type | Filter | Delivers to |
|---|---|---|---|
| `mag10-processed-signals-sub` | Push | none | CF archive |

CF archive receives all signal types and routes internally by `signal_type`.
No per-signal-type filtered subscriptions are needed since routing is done
in code.

---

## Message Attributes

The Detection VM sets a Pub/Sub **message attribute** on every message
published to `mag10-processed-signals`:

| Attribute | Values |
|---|---|
| `signal_type` | `volume_spike`, `momentum_signal`, `volatility_spike`, `sector_snapshot` |

This attribute is available to CF archive without parsing the message body,
enabling efficient routing.

---

## Message Format

All messages:
- Are JSON-encoded, UTF-8 bytes.
- Are published with no ordering key.

---

## Raw Trade Schema (mag10-raw-trades)

```json
{
  "s": "NVDA",
  "p": 875.30,
  "v": 48200,
  "t": 1715172043000
}
```

| Field | Type | Description |
|---|---|---|
| `s` | string | Symbol |
| `p` | float | Trade price (USD) |
| `v` | float | Trade volume |
| `t` | integer | Trade timestamp (Unix ms) |

---

## Processed Signal Schemas (mag10-processed-signals)

### volume_spike

```json
{
  "signal_type": "volume_spike",
  "symbol": "NVDA",
  "price": 875.30,
  "trade_volume": 48200,
  "avg_volume": 11800.50,
  "spike_ratio": 4.08,
  "window_trade_count": 2341,
  "window_span_secs": 298.4,
  "trade_ts": 1715172043000,
  "detected_at": "2024-05-08T14:07:23.412Z"
}
```

| Field | Type | Description |
|---|---|---|
| `signal_type` | string | Always `"volume_spike"` |
| `symbol` | string | Equity symbol |
| `price` | float | Trade price (USD) |
| `trade_volume` | float | Volume of triggering trade |
| `avg_volume` | float | Rolling window average volume (excl. current trade) |
| `spike_ratio` | float | `trade_volume / avg_volume` |
| `window_trade_count` | integer | Trades in the window at signal time |
| `window_span_secs` | float | Actual time span of the window in seconds |
| `trade_ts` | integer | Trade timestamp (Unix ms) |
| `detected_at` | string | ISO 8601 UTC signal emission time |

---

### momentum_signal

```json
{
  "signal_type": "momentum_signal",
  "symbol": "TSLA",
  "direction": "DOWN",
  "candles_in_direction": 4,
  "total_candles": 5,
  "oldest_open": 164.10,
  "latest_close": 162.80,
  "pct_change": -0.792,
  "window_start_ts": 1715171880000,
  "window_end_ts": 1715172180000,
  "detected_at": "2024-05-08T14:09:48.017Z"
}
```

| Field | Type | Description |
|---|---|---|
| `signal_type` | string | Always `"momentum_signal"` |
| `symbol` | string | Equity symbol |
| `direction` | string | `"UP"` or `"DOWN"` |
| `candles_in_direction` | integer | Candles agreeing on direction |
| `total_candles` | integer | Total candles evaluated |
| `oldest_open` | float | Open price of the oldest candle |
| `latest_close` | float | Close price of the newest candle |
| `pct_change` | float | `(latest_close - oldest_open) / oldest_open * 100` |
| `window_start_ts` | integer | Unix ms start of oldest candle's minute |
| `window_end_ts` | integer | Unix ms end of newest candle's minute |
| `detected_at` | string | ISO 8601 UTC signal emission time |

---

### volatility_spike

```json
{
  "signal_type": "volatility_spike",
  "symbol": "AMD",
  "price": 163.40,
  "mean_price": 158.4820,
  "std_dev": 1.9760,
  "z_score": 2.503,
  "window_trade_count": 1872,
  "window_span_secs": 299.6,
  "trade_ts": 1715172301000,
  "detected_at": "2024-05-08T14:11:41.889Z"
}
```

| Field | Type | Description |
|---|---|---|
| `signal_type` | string | Always `"volatility_spike"` |
| `symbol` | string | Equity symbol |
| `price` | float | Triggering trade price |
| `mean_price` | float | Window mean price |
| `std_dev` | float | Population std dev of window prices |
| `z_score` | float | `abs(price - mean_price) / std_dev` |
| `window_trade_count` | integer | Trades in the window at signal time |
| `window_span_secs` | float | Actual time span of the window in seconds |
| `trade_ts` | integer | Trade timestamp (Unix ms) |
| `detected_at` | string | ISO 8601 UTC signal emission time |

---

### sector_snapshot

```json
{
  "signal_type": "sector_snapshot",
  "snapshot_ts": "2024-05-08T14:15:00.003Z",
  "symbols": [
    {
      "symbol": "AAPL",
      "last_price": 183.12,
      "open_price": 182.50,
      "pct_change": 0.340,
      "trade_count": 1842,
      "total_volume": 482300,
      "last_trade_ts": 1715172899000,
      "is_stale": false
    }
  ]
}
```

| Field | Type | Description |
|---|---|---|
| `signal_type` | string | Always `"sector_snapshot"` |
| `snapshot_ts` | string | ISO 8601 UTC time of snapshot |
| `symbols` | array | Exactly 10 entries, one per tracked symbol |

Per-symbol fields:

| Field | Type | Description |
|---|---|---|
| `symbol` | string | Equity symbol |
| `last_price` | float or null | Most recent trade price |
| `open_price` | float or null | First trade price this session |
| `pct_change` | float or null | Session price change % |
| `trade_count` | integer | Trades received this session |
| `total_volume` | float | Cumulative session volume |
| `last_trade_ts` | integer or null | Last trade timestamp (Unix ms) |
| `is_stale` | boolean | True if no trade in last `SECTOR_STALE_SECS` seconds |

---

## Delivery Guarantees

Pub/Sub provides at-least-once delivery. CF archive and CF gcs-to-bq must
both be idempotent — receiving the same message or GCS event twice must
produce the same outcome.
