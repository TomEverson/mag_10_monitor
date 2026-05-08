import base64
import hashlib
import json
import logging
import os
from datetime import datetime, timezone

import functions_framework
from google.cloud import storage
from pydantic import ValidationError

from shared import bq_client
from shared.models import MomentumSignal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_GCS_BUCKET = os.environ["GCS_BUCKET_RAW"]
_TABLE = "{}.{}.momentum_signals".format(
    os.environ["GCP_PROJECT_ID"], os.environ["BQ_DATASET"]
)

_gcs = storage.Client()
_bucket = _gcs.bucket(_GCS_BUCKET)


def _ms_to_bq(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def _now_bq() -> str:
    return datetime.now(timezone.utc).isoformat()


@functions_framework.http
def handle(request):
    # 1. Parse Pub/Sub envelope
    envelope = request.get_json(silent=True)
    if not envelope or "message" not in envelope:
        logger.error("Missing Pub/Sub envelope")
        return "Bad Request: missing Pub/Sub envelope", 400
    try:
        raw = base64.b64decode(envelope["message"]["data"])
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        logger.error("Failed to decode message: %s", exc)
        return f"Bad Request: {exc}", 400

    # 2. Validate
    try:
        event = MomentumSignal.model_validate(payload)
    except ValidationError as exc:
        logger.error("Validation failed for momentum_signal: %s", exc)
        return f"Bad Request: {exc}", 400

    # 3. Archive raw event to GCS
    detected_dt = datetime.fromisoformat(event.detected_at.replace("Z", "+00:00"))
    gcs_path = (
        f"momentum_signal/{detected_dt.year:04d}/{detected_dt.month:02d}/"
        f"{detected_dt.day:02d}/{event.detected_at}_{event.symbol}.json"
    )
    try:
        _bucket.blob(gcs_path).upload_from_string(raw, content_type="application/json")
    except Exception as exc:
        logger.error("GCS write failed for %s: %s", event.symbol, exc)
        return "Internal Server Error: GCS write failed", 500

    # 4. Enrich and build BQ row
    # Partition column is window_end_ts, not a per-trade timestamp
    row = {
        "window_end_ts": _ms_to_bq(event.window_end_ts),
        "detected_at": event.detected_at.replace("Z", "+00:00"),
        "processed_at": _now_bq(),
        "symbol": event.symbol,
        "direction": event.direction,
        "candles_in_direction": event.candles_in_direction,
        "total_candles": event.total_candles,
        "oldest_open": event.oldest_open,
        "latest_close": event.latest_close,
        "pct_change": event.pct_change,
        "window_start_ts": _ms_to_bq(event.window_start_ts),
    }
    insert_id = hashlib.md5(f"{event.window_end_ts}:{event.symbol}".encode()).hexdigest()

    # 5. Write to BigQuery
    try:
        bq_client.insert_rows(_TABLE, [row], [insert_id])
    except Exception as exc:
        logger.error("BigQuery insert failed for %s: %s", event.symbol, exc)
        return "Internal Server Error: BigQuery insert failed", 500

    return "OK", 200
