import hashlib
import json
import logging
import os
from datetime import datetime, timezone

import functions_framework
from google.cloud import storage
from pydantic import ValidationError

from shared import bq_client
from shared.models import MomentumSignal, SectorSnapshot, VolatilitySpike, VolumeSpike

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_PROJECT_ID = os.environ["GCP_PROJECT_ID"]
_DATASET = os.environ["BQ_DATASET"]

_gcs = storage.Client()

_SIGNAL_TYPE_BY_PREFIX = {
    "silver/volume/":     "volume_spike",
    "silver/momentum/":   "momentum_signal",
    "silver/volatility/": "volatility_spike",
    "silver/sector/":     "sector_snapshot",
}

_MODEL_BY_TYPE = {
    "volume_spike":     VolumeSpike,
    "momentum_signal":  MomentumSignal,
    "volatility_spike": VolatilitySpike,
    "sector_snapshot":  SectorSnapshot,
}

_TABLE_BY_TYPE = {
    "volume_spike":     f"{_PROJECT_ID}.{_DATASET}.volume_spikes",
    "momentum_signal":  f"{_PROJECT_ID}.{_DATASET}.momentum_signals",
    "volatility_spike": f"{_PROJECT_ID}.{_DATASET}.volatility_spikes",
    "sector_snapshot":  f"{_PROJECT_ID}.{_DATASET}.sector_snapshots",
}


def _ms_to_bq(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def _now_bq() -> str:
    return datetime.now(timezone.utc).isoformat()


def _signal_type_from_path(object_path: str) -> str | None:
    for prefix, signal_type in _SIGNAL_TYPE_BY_PREFIX.items():
        if object_path.startswith(prefix):
            return signal_type
    return None


def _build_row(signal_type: str, event, processed_at: str) -> tuple[dict, str]:
    """Returns (bq_row, insert_id)."""
    if signal_type == "volume_spike":
        row = {
            "timestamp":          _ms_to_bq(event.trade_ts),
            "detected_at":        event.detected_at.replace("Z", "+00:00"),
            "processed_at":       processed_at,
            "symbol":             event.symbol,
            "price":              event.price,
            "trade_volume":       event.trade_volume,
            "avg_volume":         event.avg_volume,
            "spike_ratio":        event.spike_ratio,
            "window_trade_count": event.window_trade_count,
            "window_span_secs":   event.window_span_secs,
        }
        insert_id = hashlib.md5(f"{event.detected_at}:{event.symbol}".encode()).hexdigest()
        return row, insert_id

    if signal_type == "momentum_signal":
        row = {
            "window_end_ts":        _ms_to_bq(event.window_end_ts),
            "detected_at":          event.detected_at.replace("Z", "+00:00"),
            "processed_at":         processed_at,
            "symbol":               event.symbol,
            "direction":            event.direction,
            "candles_in_direction": event.candles_in_direction,
            "total_candles":        event.total_candles,
            "oldest_open":          event.oldest_open,
            "latest_close":         event.latest_close,
            "pct_change":           event.pct_change,
            "window_start_ts":      _ms_to_bq(event.window_start_ts),
        }
        insert_id = hashlib.md5(f"{event.window_end_ts}:{event.symbol}".encode()).hexdigest()
        return row, insert_id

    if signal_type == "volatility_spike":
        row = {
            "timestamp":          _ms_to_bq(event.trade_ts),
            "detected_at":        event.detected_at.replace("Z", "+00:00"),
            "processed_at":       processed_at,
            "symbol":             event.symbol,
            "price":              event.price,
            "mean_price":         event.mean_price,
            "std_dev":            event.std_dev,
            "z_score":            event.z_score,
            "window_trade_count": event.window_trade_count,
            "window_span_secs":   event.window_span_secs,
        }
        insert_id = hashlib.md5(f"{event.detected_at}:{event.symbol}".encode()).hexdigest()
        return row, insert_id

    # sector_snapshot — one row per symbol
    raise ValueError("Use _build_sector_rows for sector_snapshot")


def _build_sector_rows(event: SectorSnapshot, processed_at: str) -> tuple[list[dict], list[str]]:
    rows, ids = [], []
    for sym in event.symbols:
        row = {
            "snapshot_ts":   event.snapshot_ts.replace("Z", "+00:00"),
            "processed_at":  processed_at,
            "symbol":        sym.symbol,
            "last_price":    sym.last_price,
            "open_price":    sym.open_price,
            "pct_change":    sym.pct_change,
            "trade_count":   sym.trade_count,
            "total_volume":  sym.total_volume,
            "last_trade_ts": _ms_to_bq(sym.last_trade_ts) if sym.last_trade_ts is not None else None,
            "is_stale":      sym.is_stale,
        }
        rows.append(row)
        ids.append(hashlib.md5(f"{event.snapshot_ts}:{sym.symbol}".encode()).hexdigest())
    return rows, ids


@functions_framework.cloud_event
def handle(cloud_event):
    data = cloud_event.data
    bucket_name = data["bucket"]
    object_path = data["name"]

    logger.info("GCS event: gs://%s/%s", bucket_name, object_path)

    # 1. Determine signal type from path
    signal_type = _signal_type_from_path(object_path)
    if signal_type is None:
        logger.error("Unknown GCS path prefix: %s — skipping", object_path)
        return

    # 2. Download file from GCS
    try:
        bucket = _gcs.bucket(bucket_name)
        raw = bucket.blob(object_path).download_as_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        logger.error("Failed to read GCS object %s: %s", object_path, exc)
        raise  # triggers GCS retry

    # 3. Validate
    try:
        event = _MODEL_BY_TYPE[signal_type].model_validate(payload)
    except ValidationError as exc:
        logger.error("Validation failed for %s (%s): %s", signal_type, object_path, exc)
        return  # don't retry bad data

    # 4. Write to BigQuery
    processed_at = _now_bq()
    table = _TABLE_BY_TYPE[signal_type]

    try:
        if signal_type == "sector_snapshot":
            rows, ids = _build_sector_rows(event, processed_at)
        else:
            row, insert_id = _build_row(signal_type, event, processed_at)
            rows, ids = [row], [insert_id]

        bq_client.insert_rows(table, rows, ids)
        logger.info("Inserted %d row(s) into %s", len(rows), table)

    except Exception as exc:
        logger.error("BigQuery insert failed for %s: %s", object_path, exc)
        raise  # triggers GCS retry
