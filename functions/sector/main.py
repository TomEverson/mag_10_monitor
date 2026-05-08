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
from shared.models import SectorSnapshot

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_GCS_BUCKET = os.environ["GCS_BUCKET_RAW"]
_TABLE = "{}.{}.sector_snapshots".format(
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
        event = SectorSnapshot.model_validate(payload)
    except ValidationError as exc:
        logger.error("Validation failed for sector_snapshot: %s", exc)
        return f"Bad Request: {exc}", 400

    # 3. Archive full snapshot to GCS (one file per message, not per symbol)
    snapshot_dt = datetime.fromisoformat(event.snapshot_ts.replace("Z", "+00:00"))
    gcs_path = (
        f"sector_snapshot/{snapshot_dt.year:04d}/{snapshot_dt.month:02d}/"
        f"{snapshot_dt.day:02d}/{event.snapshot_ts}.json"
    )
    try:
        _bucket.blob(gcs_path).upload_from_string(raw, content_type="application/json")
    except Exception as exc:
        logger.error("GCS write failed for sector snapshot %s: %s", event.snapshot_ts, exc)
        return "Internal Server Error: GCS write failed", 500

    # 4. Build one BQ row per symbol and insert all 10 in a single call
    snapshot_ts_bq = event.snapshot_ts.replace("Z", "+00:00")
    processed_at = _now_bq()

    rows = []
    row_ids = []
    for sym in event.symbols:
        row = {
            "snapshot_ts": snapshot_ts_bq,
            "processed_at": processed_at,
            "symbol": sym.symbol,
            "last_price": sym.last_price,
            "open_price": sym.open_price,
            "pct_change": sym.pct_change,
            "trade_count": sym.trade_count,
            "total_volume": sym.total_volume,
            "last_trade_ts": _ms_to_bq(sym.last_trade_ts) if sym.last_trade_ts is not None else None,
            "is_stale": sym.is_stale,
        }
        rows.append(row)
        row_ids.append(
            hashlib.md5(f"{event.snapshot_ts}:{sym.symbol}".encode()).hexdigest()
        )

    # 5. Write all 10 rows to BigQuery in one request
    try:
        bq_client.insert_rows(_TABLE, rows, row_ids)
    except Exception as exc:
        logger.error("BigQuery insert failed for sector snapshot %s: %s", event.snapshot_ts, exc)
        return "Internal Server Error: BigQuery insert failed", 500

    return "OK", 200
