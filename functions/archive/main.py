import base64
import json
import logging
import os
from datetime import datetime, timezone

import functions_framework
from google.cloud import storage
from pydantic import ValidationError

from shared.models import MomentumSignal, SectorSnapshot, VolatilitySpike, VolumeSpike

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_GCS_BUCKET = os.environ["GCS_BUCKET_RAW"]

_gcs = storage.Client()
_bucket = _gcs.bucket(_GCS_BUCKET)

_MODELS = {
    "volume_spike":     VolumeSpike,
    "momentum_signal":  MomentumSignal,
    "volatility_spike": VolatilitySpike,
    "sector_snapshot":  SectorSnapshot,
}

_GCS_PREFIX = {
    "volume_spike":     "silver/volume",
    "momentum_signal":  "silver/momentum",
    "volatility_spike": "silver/volatility",
    "sector_snapshot":  "silver/sector",
}


def _gcs_path(signal_type: str, payload: dict) -> str:
    if signal_type == "sector_snapshot":
        ts = payload.get("snapshot_ts", "unknown")
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return (
            f"{_GCS_PREFIX[signal_type]}/"
            f"{dt.year:04d}/{dt.month:02d}/{dt.day:02d}/{ts}.json"
        )
    ts = payload.get("detected_at", "unknown")
    symbol = payload.get("symbol", "unknown")
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return (
        f"{_GCS_PREFIX[signal_type]}/"
        f"{dt.year:04d}/{dt.month:02d}/{dt.day:02d}/{ts}_{symbol}.json"
    )


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

    # 2. Determine signal_type — prefer message attribute, fall back to payload field
    signal_type = (
        envelope["message"].get("attributes", {}).get("signal_type")
        or payload.get("signal_type")
    )

    if signal_type not in _MODELS:
        logger.error("Unknown signal_type: %s", signal_type)
        return f"Bad Request: unknown signal_type '{signal_type}'", 400

    # 3. Validate payload
    try:
        _MODELS[signal_type].model_validate(payload)
    except ValidationError as exc:
        logger.error("Validation failed for %s: %s", signal_type, exc)
        return f"Bad Request: {exc}", 400

    # 4. Write raw JSON to GCS Silver
    gcs_path = _gcs_path(signal_type, payload)
    try:
        _bucket.blob(gcs_path).upload_from_string(raw, content_type="application/json")
        logger.info("Archived %s to %s", signal_type, gcs_path)
    except Exception as exc:
        logger.error("GCS write failed for %s: %s", signal_type, exc)
        return "Internal Server Error: GCS write failed", 500

    return "OK", 200
