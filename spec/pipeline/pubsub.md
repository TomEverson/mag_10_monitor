# Spec: Pub/Sub Topics & Message Schemas

## Topics

| Topic name                  | Published by | Consumed by         | Trigger |
|-----------------------------|--------------|---------------------|---------|
| `mag10-volume-spike`        | listener     | functions/volume    | On volume threshold breach |
| `mag10-momentum-signal`     | listener     | functions/momentum  | On momentum threshold breach |
| `mag10-volatility-spike`    | listener     | functions/volatility| On volatility threshold breach |
| `mag10-sector-snapshot`     | listener     | functions/sector    | Every 60 seconds |

All topic names are stored in environment variables — the listener reads them
from `PUBSUB_TOPIC_VOLUME`, `PUBSUB_TOPIC_MOMENTUM`, `PUBSUB_TOPIC_VOLATILITY`,
and `PUBSUB_TOPIC_SECTOR`. The Terraform infra creates the topics with these
exact names.

---

## Message Format

All messages:

- Are JSON-encoded, UTF-8 bytes.
- Carry no Pub/Sub message attributes (all metadata is in the JSON body).
- Are published with no ordering key.

---

## Subscriptions

Each Cloud Function is triggered by exactly one push subscription. Subscription
names follow the convention `mag10-{signal}-sub`.

| Subscription              | Delivers to         |
|---------------------------|---------------------|
| `mag10-volume-spike-sub`  | functions/volume    |
| `mag10-momentum-signal-sub` | functions/momentum |
| `mag10-volatility-spike-sub` | functions/volatility |
| `mag10-sector-snapshot-sub` | functions/sector   |

Subscriptions use **push delivery** to Cloud Function HTTP endpoints. The
Cloud Functions Gen 2 framework handles Pub/Sub push message unwrapping
automatically.

---

## Message Schemas

### mag10-volume-spike

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

| Field          | Type    | Required | Description |
|----------------|---------|----------|-------------|
| `signal_type`  | string  | Yes      | Always `"volume_spike"` |
| `symbol`       | string  | Yes      | Equity symbol |
| `price`        | float   | Yes      | Trade price (USD) |
| `trade_volume` | float   | Yes      | Volume of triggering trade |
| `avg_volume`   | float   | Yes      | Rolling average volume (excl. current trade) |
| `spike_ratio`  | float   | Yes      | `trade_volume / avg_volume` |
| `window_size`  | integer | Yes      | Trades in the window at signal time |
| `trade_ts`     | integer | Yes      | Trade timestamp (Unix ms) |
| `detected_at`  | string  | Yes      | ISO 8601 UTC signal emission time |

---

### mag10-momentum-signal

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

| Field           | Type    | Required | Description |
|-----------------|---------|----------|-------------|
| `signal_type`   | string  | Yes      | Always `"momentum_signal"` |
| `symbol`        | string  | Yes      | Equity symbol |
| `direction`     | string  | Yes      | `"UP"` or `"DOWN"` |
| `current_price` | float   | Yes      | Triggering trade price |
| `anchor_price`  | float   | Yes      | Oldest price in window |
| `pct_change`    | float   | Yes      | Percentage change, negative for DOWN |
| `window_size`   | integer | Yes      | Trades in the window at signal time |
| `trade_ts`      | integer | Yes      | Trade timestamp (Unix ms) |
| `detected_at`   | string  | Yes      | ISO 8601 UTC signal emission time |

---

### mag10-volatility-spike

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

| Field         | Type    | Required | Description |
|---------------|---------|----------|-------------|
| `signal_type` | string  | Yes      | Always `"volatility_spike"` |
| `symbol`      | string  | Yes      | Equity symbol |
| `price`       | float   | Yes      | Triggering trade price |
| `mean_price`  | float   | Yes      | Window mean price |
| `std_dev`     | float   | Yes      | Population std dev of window prices |
| `z_score`     | float   | Yes      | `abs(price - mean_price) / std_dev` |
| `window_size` | integer | Yes      | Trades in the window at signal time |
| `trade_ts`    | integer | Yes      | Trade timestamp (Unix ms) |
| `detected_at` | string  | Yes      | ISO 8601 UTC signal emission time |

---

### mag10-sector-snapshot

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

Top-level fields:

| Field          | Type   | Required | Description |
|----------------|--------|----------|-------------|
| `signal_type`  | string | Yes      | Always `"sector_snapshot"` |
| `snapshot_ts`  | string | Yes      | ISO 8601 UTC time of snapshot |
| `symbols`      | array  | Yes      | Exactly 10 entries, one per tracked symbol |

Per-symbol fields:

| Field           | Type            | Required | Description |
|-----------------|-----------------|----------|-------------|
| `symbol`        | string          | Yes      | Equity symbol |
| `last_price`    | float or null   | Yes      | Most recent trade price; null if unseen |
| `open_price`    | float or null   | Yes      | First trade price this session; null if unseen |
| `pct_change`    | float or null   | Yes      | Session price change %; null if price unavailable |
| `trade_count`   | integer         | Yes      | Trades received this session |
| `total_volume`  | float           | Yes      | Cumulative session volume |
| `last_trade_ts` | integer or null | Yes      | Last trade timestamp (Unix ms); null if unseen |
| `is_stale`      | boolean         | Yes      | True if no trade in last `SECTOR_STALE_SECS` seconds |

---

## Delivery Guarantees

Pub/Sub provides at-least-once delivery. Cloud Functions must be idempotent —
receiving the same message twice must produce the same outcome (see
`spec/pipeline/functions.md`).
