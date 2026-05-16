import statistics
import time
from collections import defaultdict, deque
from datetime import datetime, timezone

from config import (
    VOLATILITY_COOLDOWN_SECS,
    VOLATILITY_MIN_WINDOW_SECS,
    VOLATILITY_WINDOW_SECS,
    VOLATILITY_Z_THRESHOLD,
)
from detectors.base import BaseDetector


def _now_z() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class VolatilityDetector(BaseDetector):
    def __init__(self) -> None:
        # symbol → deque of (timestamp_ms, price)
        self._windows: dict[str, deque[tuple[int, float]]] = defaultdict(deque)
        self._cooldowns: dict[str, float] = {}

    def process(self, trade: dict) -> dict | None:
        symbol: str = trade["s"]
        price: float = trade["p"]
        trade_ts: int = trade["t"]

        window = self._windows[symbol]
        window.append((trade_ts, price))

        # Prune stale entries
        cutoff = trade_ts - VOLATILITY_WINDOW_SECS * 1000
        while window and window[0][0] < cutoff:
            window.popleft()

        if len(window) < 2:
            return None

        span_ms = window[-1][0] - window[0][0]
        if span_ms < VOLATILITY_MIN_WINDOW_SECS * 1000:
            return None

        if time.monotonic() - self._cooldowns.get(symbol, 0.0) < VOLATILITY_COOLDOWN_SECS:
            return None

        prices = [p for _, p in window]
        mean_price = statistics.mean(prices)
        std_dev = statistics.pstdev(prices)  # population std dev

        if std_dev == 0:
            return None

        z_score = abs(price - mean_price) / std_dev
        if z_score < VOLATILITY_Z_THRESHOLD:
            return None

        self._cooldowns[symbol] = time.monotonic()

        return {
            "signal_type": "volatility_spike",
            "symbol": symbol,
            "price": price,
            "mean_price": round(mean_price, 4),
            "std_dev": round(std_dev, 4),
            "z_score": round(z_score, 3),
            "window_trade_count": len(window),
            "window_span_secs": round(span_ms / 1000, 1),
            "trade_ts": trade_ts,
            "detected_at": _now_z(),
        }

    def reset(self) -> None:
        self._windows.clear()
        self._cooldowns.clear()
