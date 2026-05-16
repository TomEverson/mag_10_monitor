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

FINNHUB_API_KEY: str = os.environ["FINNHUB_API_KEY"]
GCP_PROJECT_ID: str = os.environ["GCP_PROJECT_ID"]
PUBSUB_TOPIC_RAW_TRADES: str = os.environ["PUBSUB_TOPIC_RAW_TRADES"]

FINNHUB_WS_URL: str = f"wss://ws.finnhub.io?token={FINNHUB_API_KEY}"
