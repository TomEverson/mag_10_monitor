from pydantic import BaseModel


class VolumeSpike(BaseModel):
    signal_type: str
    symbol: str
    price: float
    trade_volume: float
    avg_volume: float
    spike_ratio: float
    window_trade_count: int
    window_span_secs: float
    trade_ts: int
    detected_at: str


class MomentumSignal(BaseModel):
    signal_type: str
    symbol: str
    direction: str
    candles_in_direction: int
    total_candles: int
    oldest_open: float
    latest_close: float
    pct_change: float
    window_start_ts: int
    window_end_ts: int
    detected_at: str


class VolatilitySpike(BaseModel):
    signal_type: str
    symbol: str
    price: float
    mean_price: float
    std_dev: float
    z_score: float
    window_trade_count: int
    window_span_secs: float
    trade_ts: int
    detected_at: str


class SectorSymbolEntry(BaseModel):
    symbol: str
    last_price: float | None
    open_price: float | None
    pct_change: float | None
    trade_count: int
    total_volume: float
    last_trade_ts: int | None
    is_stale: bool


class SectorSnapshot(BaseModel):
    signal_type: str
    snapshot_ts: str
    symbols: list[SectorSymbolEntry]
