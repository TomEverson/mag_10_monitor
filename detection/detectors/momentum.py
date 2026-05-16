import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone

from config import (
    MOMENTUM_CANDLE_WINDOW,
    MOMENTUM_COOLDOWN_SECS,
    MOMENTUM_MIN_AGREE,
)
from detectors.base import BaseDetector


def _now_z() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass
class _Candle:
    minute: int   # trade_ts // 60_000  (identifies which calendar minute)
    open: float
    high: float
    low: float
    close: float
    volume: float


class MomentumDetector(BaseDetector):
    def __init__(self) -> None:
        # symbol → in-progress candle (None until first trade arrives)
        self._current: dict[str, _Candle | None] = defaultdict(lambda: None)
        # symbol → deque of completed candles (capped at MOMENTUM_CANDLE_WINDOW)
        self._completed: dict[str, deque[_Candle]] = defaultdict(
            lambda: deque(maxlen=MOMENTUM_CANDLE_WINDOW)
        )
        self._cooldowns: dict[str, float] = {}

    def process(self, trade: dict) -> dict | None:
        symbol: str = trade["s"]
        price: float = trade["p"]
        volume: float = trade["v"]
        trade_ts: int = trade["t"]
        minute = trade_ts // 60_000

        current = self._current[symbol]

        if current is None:
            self._current[symbol] = _Candle(
                minute=minute,
                open=price, high=price, low=price, close=price, volume=volume,
            )
            return None

        if minute == current.minute:
            current.high = max(current.high, price)
            current.low = min(current.low, price)
            current.close = price
            current.volume += volume
            return None

        if minute > current.minute:
            # Current minute is complete — finalise and start a new candle
            self._completed[symbol].append(current)
            self._current[symbol] = _Candle(
                minute=minute,
                open=price, high=price, low=price, close=price, volume=volume,
            )
            return self._check_signal(symbol)

        # Late trade (minute < current.minute) — ignore for candle purposes
        return None

    def _check_signal(self, symbol: str) -> dict | None:
        completed = self._completed[symbol]
        if len(completed) < MOMENTUM_CANDLE_WINDOW:
            return None

        if time.monotonic() - self._cooldowns.get(symbol, 0.0) < MOMENTUM_COOLDOWN_SECS:
            return None

        up_count = sum(1 for c in completed if c.close >= c.open)
        down_count = MOMENTUM_CANDLE_WINDOW - up_count

        if up_count >= MOMENTUM_MIN_AGREE:
            direction = "UP"
            candles_in_direction = up_count
        elif down_count >= MOMENTUM_MIN_AGREE:
            direction = "DOWN"
            candles_in_direction = down_count
        else:
            return None

        oldest = completed[0]
        newest = completed[-1]

        if oldest.open == 0:
            return None

        pct_change = round((newest.close - oldest.open) / oldest.open * 100, 3)
        window_start_ts = oldest.minute * 60_000
        window_end_ts = (newest.minute + 1) * 60_000 - 1

        self._cooldowns[symbol] = time.monotonic()

        return {
            "signal_type": "momentum_signal",
            "symbol": symbol,
            "direction": direction,
            "candles_in_direction": candles_in_direction,
            "total_candles": MOMENTUM_CANDLE_WINDOW,
            "oldest_open": oldest.open,
            "latest_close": newest.close,
            "pct_change": pct_change,
            "window_start_ts": window_start_ts,
            "window_end_ts": window_end_ts,
            "detected_at": _now_z(),
        }

    def reset(self) -> None:
        self._current.clear()
        self._completed.clear()
        self._cooldowns.clear()
