import json
import logging
import time
from datetime import datetime, timezone

from google.cloud import storage

from config import GCS_BUCKET, WARM_START_LOOKBACK_SECS

logger = logging.getLogger(__name__)

_gcs = storage.Client()


def _bronze_prefix_for(dt: datetime) -> str:
    return f"bronze/{dt.year:04d}/{dt.month:02d}/{dt.day:02d}/"


def load_recent_trades() -> list[dict]:
    """
    List and download raw trade files from GCS Bronze written in the last
    WARM_START_LOOKBACK_SECS seconds. Returns trades sorted oldest-first.
    """
    now_ms = time.time() * 1000
    cutoff_ms = now_ms - WARM_START_LOOKBACK_SECS * 1000

    bucket = _gcs.bucket(GCS_BUCKET)
    today = datetime.now(timezone.utc)
    prefix = _bronze_prefix_for(today)

    trades: list[dict] = []

    try:
        blobs = list(bucket.list_blobs(prefix=prefix))
        logger.info("Warm-start: found %d Bronze objects under %s", len(blobs), prefix)

        for blob in blobs:
            # Filename format: {trade_ts_ms}_{symbol}.json
            filename = blob.name.split("/")[-1]
            try:
                trade_ts_ms = int(filename.split("_")[0])
            except (ValueError, IndexError):
                continue

            if trade_ts_ms < cutoff_ms:
                continue

            try:
                raw = blob.download_as_bytes()
                trade = json.loads(raw)
                trades.append(trade)
            except Exception as exc:
                logger.warning("Warm-start: failed to load %s: %s", blob.name, exc)

    except Exception as exc:
        logger.warning("Warm-start: GCS listing failed: %s", exc)

    trades.sort(key=lambda t: t.get("t", 0))
    logger.info("Warm-start: loaded %d trades (lookback %ds)", len(trades), WARM_START_LOOKBACK_SECS)
    return trades


def warm_start(detectors: list) -> None:
    """
    Feed recent Bronze trades through all detectors to rebuild rolling windows.
    Signals emitted during warm-start are discarded — they are replays.
    """
    trades = load_recent_trades()
    if not trades:
        logger.info("Warm-start: no Bronze data found — detectors starting cold")
        return

    replayed = 0
    for trade in trades:
        for detector in detectors:
            detector.process(trade)
        replayed += 1

    logger.info("Warm-start complete: replayed %d trades through detectors", replayed)
