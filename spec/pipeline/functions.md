# Spec: Cloud Functions

## Overview

There are four Cloud Functions, one per Pub/Sub topic. Each function is
deployed independently as a Cloud Functions Gen 2 HTTP function triggered by
a Pub/Sub push subscription. Functions share no state with each other or with
the listener.

---

## Common Responsibilities (all functions)

Every function must perform these steps in order:

1. **Parse the Pub/Sub envelope** — unwrap the base64-encoded `data` field
   from the Pub/Sub push payload and decode it to a JSON dict.
2. **Validate the payload** — use the Pydantic model from `shared/models.py`
   to validate the decoded dict. If validation fails, log at ERROR and return
   HTTP 400 (Pub/Sub will not redeliver on 4xx).
3. **Archive to GCS** — write the raw JSON bytes to GCS **before** any
   transformation or enrichment. If the GCS write fails, return HTTP 500 so
   Pub/Sub redelivers.
4. **Enrich the payload** — add `processed_at` (ISO 8601 UTC timestamp of when
   the function handled the message) and any function-specific derived fields.
5. **Write to BigQuery** — stream insert the enriched row using
   `shared/bq_client.py`. If the insert fails, return HTTP 500.
6. **Return HTTP 200** — signals successful processing.

---

## Idempotency

Pub/Sub guarantees at-least-once delivery. The same message may arrive more
than once. Functions must not create duplicate rows in BigQuery.

**Deduplication key per function:**

| Function    | Key fields |
|-------------|------------|
| volume      | `detected_at` + `symbol` |
| momentum    | `window_end_ts` + `symbol` |
| volatility  | `detected_at` + `symbol` |
| sector      | `snapshot_ts` + `symbol` (per row) |

The BigQuery streaming insert buffer provides ~1-minute deduplication via
`insertId`. The `insertId` passed to `bq_client.py` must be derived
deterministically from the deduplication key:

```python
# volume / volatility
insert_id = hashlib.md5(f"{detected_at}:{symbol}".encode()).hexdigest()

# momentum
insert_id = hashlib.md5(f"{window_end_ts}:{symbol}".encode()).hexdigest()
```

For the sector snapshot, `insertId` is derived per-symbol row:

```python
insert_id = hashlib.md5(f"{snapshot_ts}:{symbol}".encode()).hexdigest()
```

---

## GCS Archive

**Bucket:** `GCS_BUCKET_RAW` (from environment variable)

**Object path pattern:**

```
{signal_type}/{YYYY}/{MM}/{DD}/{detected_at_iso}_{symbol}.json
```

For sector snapshots (which cover all symbols):

```
sector_snapshot/{YYYY}/{MM}/{DD}/{snapshot_ts_iso}.json
```

The raw JSON written to GCS is the **original decoded payload** before any
enrichment. `detected_at` and `snapshot_ts` are in ISO 8601 format; slashes
are replaced with underscores in the filename component.

---

## Enrichment Fields

Each function adds `processed_at` to the row written to BigQuery. This field
is not present in the Pub/Sub message and must be set by the function at
processing time.

| Field          | Type   | Description |
|----------------|--------|-------------|
| `processed_at` | string | ISO 8601 UTC timestamp when the function processed the message |

No other enrichment is required beyond what each function's BigQuery table
schema defines. Do not add fields not defined in `spec/pipeline/bigquery.md`.

---

## Error Handling

| Scenario | HTTP Response | Notes |
|----------|---------------|-------|
| Pub/Sub envelope malformed | 400 | Log at ERROR; no redeliver |
| Payload fails Pydantic validation | 400 | Log at ERROR with validation error detail; no redeliver |
| GCS write fails | 500 | Log at ERROR; Pub/Sub redelivers |
| BigQuery insert fails | 500 | Log at ERROR; Pub/Sub redelivers |
| Unexpected exception | 500 | Log at ERROR with full traceback; Pub/Sub redelivers |

Functions must never swallow exceptions silently. All errors must be logged
at ERROR level with the `signal_type` and (where available) `symbol` in the
log message.

---

## Individual Function Specs

### functions/volume/

- **Topic:** `mag10-volume-spike`
- **Table:** `signals.volume_spikes`
- No additional enrichment beyond `processed_at`.

### functions/momentum/

- **Topic:** `mag10-momentum-signal`
- **Table:** `signals.momentum_signals`
- No additional enrichment beyond `processed_at`.

### functions/volatility/

- **Topic:** `mag10-volatility-spike`
- **Table:** `signals.volatility_spikes`
- No additional enrichment beyond `processed_at`.

### functions/sector/

- **Topic:** `mag10-sector-snapshot`
- **Table:** `signals.sector_snapshots`
- The sector snapshot message contains 10 symbols per message. The function
  must insert **one BigQuery row per symbol** from the `symbols` array.
- The `insertId` for each row is derived per-symbol (see Idempotency).
- GCS archive writes the full message once (not one file per symbol).

---

## Shared Modules

### shared/models.py

Pydantic v2 models for each signal type. The function imports the correct model
for its topic and calls `Model.model_validate(payload)` to parse and validate.

### shared/bq_client.py

A thin wrapper around `google.cloud.bigquery.Client`. It must:

- Accept a list of row dicts and an `insert_id_field` (the field name to use
  as the BigQuery `insertId`).
- Call `client.insert_rows_json(table_ref, rows, row_ids=...)`.
- Raise an exception if `insert_rows_json` returns any errors (the return
  value is a list of error dicts — a non-empty list means partial failure).

---

## Deployment Notes

- Each function directory has its own `pyproject.toml` and `requirements.txt`.
- `requirements.txt` is generated with `uv pip compile` and must not be edited
  by hand.
- The `shared/` directory is copied into each function directory at deploy time
  (as part of the Terraform or deployment script) — it is not a Python package
  installed via pip.
- Functions run on Python 3.12.
- Memory: 256 MB per function (sufficient; these are lightweight transforms).
- Timeout: 60 seconds per invocation.
- Min instances: 0 (scale to zero when no messages).
