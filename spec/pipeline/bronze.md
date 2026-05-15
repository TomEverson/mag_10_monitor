# Spec: Bronze Layer

## Overview

The Bronze layer is the immutable raw trade archive. Every validated trade
published by the WebSocket VM lands in GCS Bronze regardless of what the
Detection VM does. It serves two purposes:

1. **Durability** — raw trades are safe even if the Detection VM crashes.
2. **Warm-start** — the Detection VM reads Bronze on startup to rebuild
   rolling window state before connecting to the WebSocket.

---

## GCS Path Structure

```
bronze/{YYYY}/{MM}/{DD}/{HH}/{trade_ts_ms}_{symbol}.json
```

Example:
```
bronze/2024/05/08/14/1715172043000_NVDA.json
```

All paths use lowercase. The file contains exactly one raw trade as JSON.

---

## Raw Trade Schema

The raw trade is the validated Finnhub trade object, written as-is with no
enrichment:

```json
{
  "s": "NVDA",
  "p": 875.30,
  "v": 48200,
  "t": 1715172043000
}
```

| Field | Type    | Description |
|-------|---------|-------------|
| `s`   | string  | Symbol |
| `p`   | float   | Trade price (USD) |
| `v`   | float   | Trade volume |
| `t`   | integer | Trade timestamp (Unix ms) |

This is the raw Finnhub format — no field renaming or enrichment.

---

## How Bronze is Written

The WebSocket VM publishes every validated raw trade to the
`mag10-raw-trades` Pub/Sub topic. A **Pub/Sub Cloud Storage subscription**
(native GCP feature, no Cloud Function required) writes each message directly
to the GCS Bronze bucket.

The Cloud Storage subscription is configured with:
- **Bucket:** `mag-10-raw`
- **Object prefix:** `bronze/`
- **Filename suffix:** `.json`
- **Max duration:** 1 second (flush quickly, one file per message)

No code is required for Bronze writes — this is entirely infrastructure.

---

## Warm-Start Procedure

When the Detection VM starts (or restarts after a crash), it must rebuild
rolling window state before connecting to the WebSocket. The warm-start
procedure:

1. Determine the required lookback window:
   `max(VOLUME_WINDOW_SECS, VOLATILITY_WINDOW_SECS)` = 300 seconds.
2. Query GCS Bronze for all trade files in the last 300 seconds across all
   10 symbols. List objects under `bronze/{today}/` filtered by
   `trade_ts >= now_ms - 300_000`.
3. For each file, download and parse the raw trade JSON.
4. Feed each trade through all four detectors via `detector.process(trade)`
   in timestamp order. Discard any signals emitted during warm-start
   (do not publish them — they are replays, not new signals).
5. Once warm-start is complete, connect to the WebSocket and resume live
   detection.

Warm-start must complete before the WebSocket connection is opened. If
warm-start fails (e.g. GCS is unavailable), the Detection VM logs a warning
and proceeds cold (detectors start with empty windows).

---

## Retention

Bronze objects are retained for **90 days** via a GCS lifecycle rule, then
deleted automatically. This matches the Silver retention policy.
