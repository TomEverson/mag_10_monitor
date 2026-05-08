import os

# Load .env for local development if python-dotenv is installed
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── Symbols ──────────────────────────────────────────────────────────────────

SYMBOLS: frozenset[str] = frozenset({
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN",
    "META", "TSLA", "AMD", "AVGO", "PLTR",
})

# ── Environment variables ─────────────────────────────────────────────────────

FINNHUB_API_KEY: str = os.environ["FINNHUB_API_KEY"]
GCP_PROJECT_ID: str = os.environ["GCP_PROJECT_ID"]
PUBSUB_TOPIC_VOLUME: str = os.environ["PUBSUB_TOPIC_VOLUME"]
PUBSUB_TOPIC_MOMENTUM: str = os.environ["PUBSUB_TOPIC_MOMENTUM"]
PUBSUB_TOPIC_VOLATILITY: str = os.environ["PUBSUB_TOPIC_VOLATILITY"]
PUBSUB_TOPIC_SECTOR: str = os.environ["PUBSUB_TOPIC_SECTOR"]

FINNHUB_WS_URL: str = f"wss://ws.finnhub.io?token={FINNHUB_API_KEY}"

# ── Volume spike detector ─────────────────────────────────────────────────────

VOLUME_WINDOW_SECS: int = 300        # 5-minute rolling window
VOLUME_MIN_WINDOW_SECS: int = 60     # must span ≥ 1 minute before firing
VOLUME_SPIKE_MULTIPLIER: float = 4.0
VOLUME_COOLDOWN_SECS: int = 180      # 3-minute cooldown per symbol

# ── Momentum detector ─────────────────────────────────────────────────────────

MOMENTUM_CANDLE_WINDOW: int = 5      # evaluate last 5 completed 1-min candles
MOMENTUM_MIN_AGREE: int = 3          # ≥ 3 candles must agree on direction
MOMENTUM_COOLDOWN_SECS: int = 120    # 2-minute cooldown per symbol

# ── Volatility spike detector ─────────────────────────────────────────────────

VOLATILITY_WINDOW_SECS: int = 300    # 5-minute rolling window
VOLATILITY_MIN_WINDOW_SECS: int = 60 # must span ≥ 1 minute before firing
VOLATILITY_Z_THRESHOLD: float = 2.5
VOLATILITY_COOLDOWN_SECS: int = 120  # 2-minute cooldown per symbol

# ── Sector snapshot ───────────────────────────────────────────────────────────

SECTOR_SNAPSHOT_INTERVAL_SECS: int = 60
SECTOR_STALE_SECS: int = 120
