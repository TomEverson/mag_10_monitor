import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

SYMBOLS: frozenset[str] = frozenset({
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN",
    "META", "TSLA", "AMD", "AVGO", "PLTR",
})

GCP_PROJECT_ID: str = os.environ["GCP_PROJECT_ID"]
PUBSUB_SUBSCRIPTION_RAW: str = os.environ["PUBSUB_SUBSCRIPTION_RAW"]
PUBSUB_TOPIC_PROCESSED: str = os.environ["PUBSUB_TOPIC_PROCESSED"]
GCS_BUCKET: str = os.environ["GCS_BUCKET"]

# ── Volume spike detector ─────────────────────────────────────────────────────

VOLUME_WINDOW_SECS: int = 300
VOLUME_MIN_WINDOW_SECS: int = 60
VOLUME_SPIKE_MULTIPLIER: float = 4.0
VOLUME_COOLDOWN_SECS: int = 180

# ── Momentum detector ─────────────────────────────────────────────────────────

MOMENTUM_CANDLE_WINDOW: int = 5
MOMENTUM_MIN_AGREE: int = 3
MOMENTUM_COOLDOWN_SECS: int = 120

# ── Volatility spike detector ─────────────────────────────────────────────────

VOLATILITY_WINDOW_SECS: int = 300
VOLATILITY_MIN_WINDOW_SECS: int = 60
VOLATILITY_Z_THRESHOLD: float = 2.5
VOLATILITY_COOLDOWN_SECS: int = 120

# ── Sector snapshot ───────────────────────────────────────────────────────────

SECTOR_SNAPSHOT_INTERVAL_SECS: int = 60
SECTOR_STALE_SECS: int = 120

# ── Warm-start ────────────────────────────────────────────────────────────────

# How far back to look in Bronze when warming up detector windows
WARM_START_LOOKBACK_SECS: int = max(VOLUME_WINDOW_SECS, VOLATILITY_WINDOW_SECS)  # 300s
