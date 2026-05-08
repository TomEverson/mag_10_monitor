import statistics
import time
from collections import defaultdict, deque
from datetime import datetime, timezone

from config import (
    VOLUME_COOLDOWN_SECS,
    VOLUME_MIN_WINDOW_SECS,
    VOLUME_SPIKE_MULTIPLIER,
    VOLUME_WINDOW_SECS,
)
from detectors.base import BaseDetector


def _now_z() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class VolumeDetector(BaseDetector):
    def __init__(self) -> None:
        # symbol → deque of (timestamp_ms, volume)
        self._windows: dict[str, deque[tuple[int, float]]] = defaultdict(deque)
        # symbol → last signal time (monotonic)
        self._cooldowns: dict[str, float] = {}

    def process(self, trade: dict) -> dict | None:
        symbol: str = trade["s"]
        price: float = trade["p"]
        volume: float = trade["v"]
        trade_ts: int = trade["t"]

        window = self._windows[symbol]
        window.append((trade_ts, volume))

        # Prune entries that have fallen outside the window
        cutoff = trade_ts - VOLUME_WINDOW_SECS * 1000
        while window and window[0][0] < cutoff:
            window.popleft()

        # Need at least two points to have a span
        if len(window) < 2:
            return None

        span_ms = window[-1][0] - window[0][0]
        if span_ms < VOLUME_MIN_WINDOW_SECS * 1000:
            return None

        # Cooldown check (wall-clock so it behaves correctly during quiet periods)
        if time.monotonic() - self._cooldowns.get(symbol, 0.0) < VOLUME_COOLDOWN_SECS:
            return None

        # Average excludes the current trade (last entry)
        prev_volumes = [v for _, v in list(window)[:-1]]
        if not prev_volumes:
            return None
        avg_volume = statistics.mean(prev_volumes)
        if avg_volume == 0:
            return None

        spike_ratio = volume / avg_volume
        if spike_ratio < VOLUME_SPIKE_MULTIPLIER:
            return None

        self._cooldowns[symbol] = time.monotonic()

        return {
            "signal_type": "volume_spike",
            "symbol": symbol,
            "price": price,
            "trade_volume": volume,
            "avg_volume": round(avg_volume, 2),
            "spike_ratio": round(spike_ratio, 2),
            "window_trade_count": len(window),
            "window_span_secs": round(span_ms / 1000, 1),
            "trade_ts": trade_ts,
            "detected_at": _now_z(),
        }

    def reset(self) -> None:
        self._windows.clear()
        self._cooldowns.clear()
