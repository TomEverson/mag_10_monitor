import time
from datetime import datetime, timezone

from config import SECTOR_STALE_SECS, SYMBOLS
from detectors.base import BaseDetector


class _SymbolState:
    __slots__ = ("last_price", "open_price", "trade_count", "total_volume", "last_trade_ts")

    def __init__(self) -> None:
        self.last_price: float | None = None
        self.open_price: float | None = None
        self.trade_count: int = 0
        self.total_volume: float = 0.0
        self.last_trade_ts: int | None = None


class SectorDetector(BaseDetector):
    def __init__(self) -> None:
        self._state: dict[str, _SymbolState] = {s: _SymbolState() for s in SYMBOLS}

    def process(self, trade: dict) -> dict | None:
        state = self._state[trade["s"]]
        if state.open_price is None:
            state.open_price = trade["p"]
        state.last_price = trade["p"]
        state.trade_count += 1
        state.total_volume += trade["v"]
        state.last_trade_ts = trade["t"]
        return None

    def get_snapshot(self) -> dict:
        now_ms = time.time() * 1000
        stale_cutoff_ms = SECTOR_STALE_SECS * 1000
        snapshot_ts = (
            datetime.now(timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )

        entries = []
        for symbol in sorted(SYMBOLS):
            st = self._state[symbol]
            last_price = st.last_price
            open_price = st.open_price
            last_trade_ts = st.last_trade_ts

            if last_price is not None and open_price is not None and open_price != 0:
                pct_change = round((last_price - open_price) / open_price * 100, 3)
            else:
                pct_change = None

            is_stale = (
                last_trade_ts is not None and (now_ms - last_trade_ts) > stale_cutoff_ms
            )

            entries.append({
                "symbol": symbol,
                "last_price": last_price,
                "open_price": open_price,
                "pct_change": pct_change,
                "trade_count": st.trade_count,
                "total_volume": st.total_volume,
                "last_trade_ts": last_trade_ts,
                "is_stale": is_stale,
            })

        return {
            "signal_type": "sector_snapshot",
            "snapshot_ts": snapshot_ts,
            "symbols": entries,
        }

    def reset(self) -> None:
        self._state = {s: _SymbolState() for s in SYMBOLS}
