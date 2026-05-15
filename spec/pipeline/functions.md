# Spec: Cloud Functions

## Overview

There are two Cloud Functions in the new architecture:

| Function | Trigger | Responsibility |
|---|---|---|
| `cf-archive` | Pub/Sub push (`mag10-processed-signals`) | Route by signal_type → write to GCS Silver |
| `cf-gcs-to-bq` | GCS object finalise (`silver/`) | Route by GCS path → write to correct BQ table |

Both functions are deployed as Cloud Functions Gen 2 HTTP functions.

---

## CF Archive

### Trigger

Pub/Sub push subscription on `mag10-processed-signals-sub`. Receives all
signal types in a single function and routes by `signal_type`.

### Responsibilities (in order)

1. **Parse the Pub/Sub envelope** — unwrap the base64-encoded `data` field
   and decode to a JSON dict.
2. **Read signal_type** — from the Pub/Sub message attribute `signal_type`
   (preferred) or from the decoded payload `signal_type` field.
3. **Validate the payload** — use the matching Pydantic model from
   `shared/models.py`. If validation fails, log at ERROR and return HTTP 400
   (Pub/Sub will not redeliver on 4xx).
4. **Write to GCS Silver** — write the raw JSON bytes to the correct Silver
   path. If the GCS write fails, return HTTP 500 so Pub/Sub redelivers.
5. **Return HTTP 200**.

CF archive does **not** write to BigQuery. Its only output is GCS Silver.

### GCS Silver Path Structure

All paths are lowercase.

```
silver/volume/{YYYY}/{MM}/{DD}/{detected_at}_{symbol}.json
silver/momentum/{YYYY}/{MM}/{DD}/{detected_at}_{symbol}.json
silver/volatility/{YYYY}/{MM}/{DD}/{detected_at}_{symbol}.json
silver/sector/{YYYY}/{MM}/{DD}/{snapshot_ts}.json
```

The prefix (`silver/volume/`, `silver/momentum/`, etc.) is determined by
`signal_type`. The raw JSON written is the **original decoded payload** before
any enrichment.

### Routing Table

| `signal_type` | GCS prefix | Pydantic model |
|---|---|---|
| `volume_spike` | `silver/volume/` | `VolumeSpike` |
| `momentum_signal` | `silver/momentum/` | `MomentumSignal` |
| `volatility_spike` | `silver/volatility/` | `VolatilitySpike` |
| `sector_snapshot` | `silver/sector/` | `SectorSnapshot` |

### Error Handling

| Scenario | HTTP Response | Notes |
|---|---|---|
| Pub/Sub envelope malformed | 400 | No redeliver |
| Unknown signal_type | 400 | Log at ERROR; no redeliver |
| Pydantic validation fails | 400 | Log at ERROR; no redeliver |
| GCS write fails | 500 | Pub/Sub redelivers |
| Unexpected exception | 500 | Pub/Sub redelivers |

---

## CF GCS-to-BQ

### Trigger

GCS object finalise event on the `silver/` prefix of bucket
`mag-10-raw`. Triggered once per file written by CF archive.

### Responsibilities (in order)

1. **Parse the GCS event** — extract the bucket name and object path from the
   Cloud Functions event payload.
2. **Determine signal_type from path** — read the first path component after
   `silver/`:
   - `silver/volume/...` → `volume_spike`
   - `silver/momentum/...` → `momentum_signal`
   - `silver/volatility/...` → `volatility_spike`
   - `silver/sector/...` → `sector_snapshot`
3. **Download the file** — read the JSON bytes from GCS.
4. **Validate the payload** — use the matching Pydantic model from
   `shared/models.py`. If validation fails, log at ERROR and return — do not
   write to BigQuery.
5. **Enrich the payload** — add `processed_at` (ISO 8601 UTC timestamp of
   when this function processed the file).
6. **Write to BigQuery** — stream insert the enriched row(s) using
   `shared/bq_client.py`. Use a deterministic `insertId` for deduplication.
7. **Return success** — GCS triggers do not use HTTP responses for retries;
   raise an exception to trigger a retry.

### Routing Table

| GCS prefix | BQ table | Rows per file |
|---|---|---|
| `silver/volume/` | `signals.volume_spikes` | 1 |
| `silver/momentum/` | `signals.momentum_signals` | 1 |
| `silver/volatility/` | `signals.volatility_spikes` | 1 |
| `silver/sector/` | `signals.sector_snapshots` | 10 (one per symbol) |

### Idempotency

| Signal type | BQ insertId key fields |
|---|---|
| `volume_spike` | `detected_at` + `symbol` |
| `momentum_signal` | `window_end_ts` + `symbol` |
| `volatility_spike` | `detected_at` + `symbol` |
| `sector_snapshot` | `snapshot_ts` + `symbol` (per row) |

```python
insert_id = hashlib.md5(f"{key_a}:{key_b}".encode()).hexdigest()
```

The BigQuery streaming insert buffer provides ~1-minute deduplication via
`insertId`. If the same GCS file triggers the function twice, the second
invocation produces the same `insertId` and BigQuery deduplicates the row.

### Enrichment Fields

| Field | Type | Description |
|---|---|---|
| `processed_at` | string | ISO 8601 UTC timestamp when cf-gcs-to-bq processed the file |

### Error Handling

| Scenario | Action |
|---|---|
| Unknown GCS path prefix | Log at ERROR; do not retry |
| File not found in GCS | Log at ERROR; do not retry |
| Pydantic validation fails | Log at ERROR; do not retry |
| BigQuery insert fails | Raise exception to trigger GCS retry |
| Unexpected exception | Raise exception to trigger GCS retry |

---

## Shared Modules

### shared/models.py

Pydantic v2 models for all four signal types. Both CF archive and CF gcs-to-bq
import from this module.

### shared/bq_client.py

Thin wrapper around `google.cloud.bigquery.Client`. Accepts a list of row
dicts and a list of `insertId` strings. Raises `RuntimeError` if
`insert_rows_json` returns any errors.

---

## Deployment Notes

- Both functions have their own `pyproject.toml` and `requirements.txt`.
- `requirements.txt` is generated with `uv pip compile` — never edited by hand.
- `shared/` is copied into each function directory at deploy time.
- Functions run on Python 3.12.
- Memory: 256 MB per function.
- Timeout: 60 seconds per invocation.
- Min instances: 0 (scale to zero when idle).

---

## Migration: Existing GCS Data

Existing signal archives use the old path structure (no `silver/` prefix).
Run the following one-time migration before deploying CF gcs-to-bq:

```bash
BUCKET=mag-10-raw

gsutil -m cp -r gs://$BUCKET/volume_spike/    gs://$BUCKET/silver/volume/
gsutil -m cp -r gs://$BUCKET/momentum_signal/ gs://$BUCKET/silver/momentum/
gsutil -m cp -r gs://$BUCKET/volatility_spike/ gs://$BUCKET/silver/volatility/
gsutil -m cp -r gs://$BUCKET/sector_snapshot/ gs://$BUCKET/silver/sector/
```

Verify the copy, then delete the old prefixes:

```bash
gsutil -m rm -r gs://$BUCKET/volume_spike/
gsutil -m rm -r gs://$BUCKET/momentum_signal/
gsutil -m rm -r gs://$BUCKET/volatility_spike/
gsutil -m rm -r gs://$BUCKET/sector_snapshot/
```
