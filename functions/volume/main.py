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
from shared.models import VolumeSpike

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_GCS_BUCKET = os.environ["GCS_BUCKET_RAW"]
_TABLE = "{}.{}.volume_spikes".format(
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
        event = VolumeSpike.model_validate(payload)
    except ValidationError as exc:
        logger.error("Validation failed for volume_spike: %s", exc)
        return f"Bad Request: {exc}", 400

    # 3. Archive raw event to GCS
    detected_dt = datetime.fromisoformat(event.detected_at.replace("Z", "+00:00"))
    gcs_path = (
        f"volume_spike/{detected_dt.year:04d}/{detected_dt.month:02d}/"
        f"{detected_dt.day:02d}/{event.detected_at}_{event.symbol}.json"
    )
    try:
        _bucket.blob(gcs_path).upload_from_string(raw, content_type="application/json")
    except Exception as exc:
        logger.error("GCS write failed for %s: %s", event.symbol, exc)
        return "Internal Server Error: GCS write failed", 500

    # 4. Enrich and build BQ row
    processed_at = _now_bq()
    row = {
        "timestamp": _ms_to_bq(event.trade_ts),
        "detected_at": event.detected_at.replace("Z", "+00:00"),
        "processed_at": processed_at,
        "symbol": event.symbol,
        "price": event.price,
        "trade_volume": event.trade_volume,
        "avg_volume": event.avg_volume,
        "spike_ratio": event.spike_ratio,
        "window_trade_count": event.window_trade_count,
        "window_span_secs": event.window_span_secs,
    }
    insert_id = hashlib.md5(f"{event.detected_at}:{event.symbol}".encode()).hexdigest()

    # 5. Write to BigQuery
    try:
        bq_client.insert_rows(_TABLE, [row], [insert_id])
    except Exception as exc:
        logger.error("BigQuery insert failed for %s: %s", event.symbol, exc)
        return "Internal Server Error: BigQuery insert failed", 500

    return "OK", 200
