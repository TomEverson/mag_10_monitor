"""BigQuery queries for MAG10 Monitor dashboard"""
import os
from datetime import datetime, timedelta
import pandas as pd
from google.cloud import bigquery

PROJECT_ID = os.getenv('GCP_PROJECT_ID', 'data-engineering-hs')
DATASET = os.getenv('BQ_DATASET', 'signals')

client = bigquery.Client(project=PROJECT_ID)

def _build_symbol_filter(symbols: list = None, col: str = 'symbol') -> str:
    """Build SQL IN clause for symbols"""
    if not symbols:
        return ""
    symbol_list = ", ".join([f"'{s}'" for s in symbols])
    return f"AND {col} IN ({symbol_list})"

# ── Chart 1: Multi-Signal Confirmation ──────────────────────────────────────
def get_multi_signal_confirmation(date_str: str, symbols: list = None):
    """Volume spikes + momentum signals within 5 minutes"""
    symbols_filter = _build_symbol_filter(symbols, 'v.symbol')

    query = f"""
    SELECT
      DATE(v.timestamp) AS date,
      v.symbol,
      v.timestamp AS volume_signal_time,
      v.spike_ratio,
      m.window_end_ts AS momentum_signal_time,
      TIMESTAMP_DIFF(m.window_end_ts, v.timestamp, SECOND) AS seconds_apart,
      v.price AS volume_price,
      m.pct_change,
      m.direction
    FROM `{PROJECT_ID}.{DATASET}.volume_spikes` v
    LEFT JOIN `{PROJECT_ID}.{DATASET}.momentum_signals` m
      ON v.symbol = m.symbol
      AND ABS(TIMESTAMP_DIFF(m.window_end_ts, v.timestamp, SECOND)) < 300
      AND DATE(m.window_end_ts) = DATE('{date_str}')
    WHERE DATE(v.timestamp) = DATE('{date_str}')
      {symbols_filter}
    ORDER BY v.timestamp DESC
    LIMIT 100
    """

    return client.query(query, job_config=bigquery.QueryJobConfig(use_query_cache=False)).to_dataframe()


# ── Chart 2: Sector Rotation Detection ──────────────────────────────────────
def get_sector_rotation(date_str: str, symbols: list = None):
    """Signal distribution by trading hour"""
    symbols_filter = _build_symbol_filter(symbols)

    query = f"""
    SELECT
      EXTRACT(HOUR FROM event_time) AS trading_hour,
      COUNT(DISTINCT symbol) AS num_signals,
      ARRAY_AGG(DISTINCT symbol ORDER BY symbol) AS symbols_signaling,
      COUNTIF(signal_type = 'volume') AS volume_count,
      COUNTIF(signal_type = 'momentum') AS momentum_count,
      COUNTIF(signal_type = 'volatility') AS volatility_count
    FROM (
      SELECT timestamp AS event_time, symbol, 'volume' AS signal_type
      FROM `{PROJECT_ID}.{DATASET}.volume_spikes`
      WHERE DATE(timestamp) = DATE('{date_str}')
        {symbols_filter}

      UNION ALL

      SELECT window_end_ts AS event_time, symbol, 'momentum' AS signal_type
      FROM `{PROJECT_ID}.{DATASET}.momentum_signals`
      WHERE DATE(window_end_ts) = DATE('{date_str}')
        {symbols_filter}

      UNION ALL

      SELECT timestamp AS event_time, symbol, 'volatility' AS signal_type
      FROM `{PROJECT_ID}.{DATASET}.volatility_spikes`
      WHERE DATE(timestamp) = DATE('{date_str}')
        {symbols_filter}
    )
    GROUP BY trading_hour
    ORDER BY trading_hour
    """

    return client.query(query, job_config=bigquery.QueryJobConfig(use_query_cache=False)).to_dataframe()


# ── Chart 3: Signal Win Rate ────────────────────────────────────────────────
def get_signal_accuracy(date_range_days: int = 30, symbols: list = None, min_spike_ratio: float = 1.0):
    """Historical win rate of volume spike signals"""
    symbols_filter = _build_symbol_filter(symbols)

    query = f"""
    WITH volume_signals AS (
      SELECT
        timestamp AS signal_time,
        symbol,
        price AS entry_price,
        spike_ratio
      FROM `{PROJECT_ID}.{DATASET}.volume_spikes`
      WHERE DATE(timestamp) >= DATE_SUB(CURRENT_DATE(), INTERVAL {date_range_days} DAY)
        AND spike_ratio >= {min_spike_ratio}
        {symbols_filter}
    ),
    sector_after AS (
      SELECT
        vs.symbol,
        vs.signal_time,
        vs.entry_price,
        vs.spike_ratio,
        ss.last_price AS exit_price,
        TIMESTAMP_DIFF(ss.snapshot_ts, vs.signal_time, MINUTE) AS minutes_later
      FROM volume_signals vs
      JOIN `{PROJECT_ID}.{DATASET}.sector_snapshots` ss
        ON vs.symbol = ss.symbol
        AND ss.snapshot_ts BETWEEN
            TIMESTAMP_ADD(vs.signal_time, INTERVAL 15 MINUTE)
            AND TIMESTAMP_ADD(vs.signal_time, INTERVAL 60 MINUTE)
        AND DATE(ss.snapshot_ts) >= DATE_SUB(CURRENT_DATE(), INTERVAL {date_range_days} DAY)
    )
    SELECT
      COUNT(*) AS total_signals,
      COUNTIF((exit_price - entry_price) / entry_price > 0.005) AS profitable_half_pct,
      COUNTIF((exit_price - entry_price) / entry_price > 0.01) AS profitable_1pct,
      COUNTIF((exit_price - entry_price) / entry_price > 0.02) AS profitable_2pct,
      ROUND(100 * COUNTIF((exit_price - entry_price) / entry_price > 0.01) / COUNT(*), 1) AS win_rate_pct,
      AVG((exit_price - entry_price) / entry_price * 100) AS avg_return_pct
    FROM sector_after
    """

    return client.query(query, job_config=bigquery.QueryJobConfig(use_query_cache=False)).to_dataframe()


# ── Chart 4: Best Trading Hours ─────────────────────────────────────────────
def get_best_hours(date_str: str, symbols: list = None):
    """Signal activity and strength by hour"""
    symbols_filter = _build_symbol_filter(symbols)

    query = f"""
    SELECT
      EXTRACT(HOUR FROM timestamp) AS trading_hour,
      COUNT(*) AS signal_count,
      AVG(spike_ratio) AS avg_spike_ratio,
      MAX(spike_ratio) AS max_spike_ratio,
      AVG(trade_volume) AS avg_trade_volume
    FROM `{PROJECT_ID}.{DATASET}.volume_spikes`
    WHERE DATE(timestamp) = DATE('{date_str}')
      {symbols_filter}
    GROUP BY trading_hour
    ORDER BY trading_hour
    """

    return client.query(query, job_config=bigquery.QueryJobConfig(use_query_cache=False)).to_dataframe()


# ── Chart 5: Volatility Regime ──────────────────────────────────────────────
def get_volatility_regime(date_range_days: int = 7, symbols: list = None):
    """Daily volatility levels"""
    symbols_filter = _build_symbol_filter(symbols)

    query = f"""
    SELECT
      DATE(timestamp) AS date,
      COUNT(*) AS volatility_signals,
      AVG(z_score) AS avg_z_score,
      MAX(z_score) AS max_z_score,
      AVG(std_dev) AS avg_std_dev,
      AVG(mean_price) AS avg_price,
      COUNT(DISTINCT symbol) AS symbols_affected
    FROM `{PROJECT_ID}.{DATASET}.volatility_spikes`
    WHERE DATE(timestamp) >= DATE_SUB(CURRENT_DATE(), INTERVAL {date_range_days} DAY)
      {symbols_filter}
    GROUP BY date
    ORDER BY date DESC
    """

    return client.query(query, job_config=bigquery.QueryJobConfig(use_query_cache=False)).to_dataframe()


# ── Chart 6: Stock Correlation ──────────────────────────────────────────────
def get_stock_correlation(date_range_days: int = 30, symbols: list = None):
    """Which stocks move together"""
    symbols_filter = _build_symbol_filter(symbols, 'v1.symbol')

    query = f"""
    SELECT
      v1.symbol AS stock_a,
      v2.symbol AS stock_b,
      COUNT(*) AS co_signal_count,
      AVG(ABS(TIMESTAMP_DIFF(v2.timestamp, v1.timestamp, SECOND))) AS avg_seconds_apart,
      AVG((v1.spike_ratio + v2.spike_ratio) / 2) AS avg_combined_spike
    FROM `{PROJECT_ID}.{DATASET}.volume_spikes` v1
    JOIN `{PROJECT_ID}.{DATASET}.volume_spikes` v2
      ON DATE(v1.timestamp) = DATE(v2.timestamp)
      AND v1.symbol < v2.symbol
      AND ABS(TIMESTAMP_DIFF(v2.timestamp, v1.timestamp, SECOND)) < 600
    WHERE DATE(v1.timestamp) >= DATE_SUB(CURRENT_DATE(), INTERVAL {date_range_days} DAY)
      {symbols_filter}
    GROUP BY stock_a, stock_b
    HAVING COUNT(*) > 1
    ORDER BY co_signal_count DESC
    LIMIT 20
    """

    return client.query(query, job_config=bigquery.QueryJobConfig(use_query_cache=False)).to_dataframe()


# ── Chart 7: Signal Strength vs Price ───────────────────────────────────────
def get_signal_strength(date_range_days: int = 30, symbols: list = None):
    """Does bigger spike ratio = bigger price move?"""
    symbols_filter = _build_symbol_filter(symbols, 'v.symbol')

    query = f"""
    WITH signal_buckets AS (
      SELECT
        v.timestamp AS signal_time,
        v.symbol,
        v.price AS entry_price,
        v.spike_ratio,
        CASE
          WHEN v.spike_ratio < 1.5 THEN 'Mild (1.0-1.5x)'
          WHEN v.spike_ratio < 2.0 THEN 'Moderate (1.5-2.0x)'
          WHEN v.spike_ratio < 3.0 THEN 'Strong (2.0-3.0x)'
          ELSE 'Extreme (3.0x+)'
        END AS breach_category
      FROM `{PROJECT_ID}.{DATASET}.volume_spikes` v
      WHERE DATE(v.timestamp) >= DATE_SUB(CURRENT_DATE(), INTERVAL {date_range_days} DAY)
        {symbols_filter}
    ),
    with_exit AS (
      SELECT
        b.breach_category,
        b.entry_price,
        ss.last_price AS exit_price,
        ROUND(100 * (ss.last_price - b.entry_price) / b.entry_price, 2) AS price_change_pct
      FROM signal_buckets b
      JOIN `{PROJECT_ID}.{DATASET}.sector_snapshots` ss
        ON b.symbol = ss.symbol
        AND ss.snapshot_ts BETWEEN
            TIMESTAMP_ADD(b.signal_time, INTERVAL 15 MINUTE)
            AND TIMESTAMP_ADD(b.signal_time, INTERVAL 30 MINUTE)
        AND DATE(ss.snapshot_ts) >= DATE_SUB(CURRENT_DATE(), INTERVAL {date_range_days} DAY)
        AND ss.is_stale = FALSE
    )
    SELECT
      breach_category,
      COUNT(*) AS occurrences,
      AVG(ABS(price_change_pct)) AS avg_price_move,
      MAX(price_change_pct) AS max_price_move,
      MIN(price_change_pct) AS min_price_move
    FROM with_exit
    GROUP BY breach_category
    ORDER BY breach_category
    """

    return client.query(query, job_config=bigquery.QueryJobConfig(use_query_cache=False)).to_dataframe()


# ── Chart 8: Real-Time Alert Board ──────────────────────────────────────────
def get_realtime_alerts(minutes_back: int = 10, symbols: list = None):
    """Live signals from the last N minutes"""
    symbols_filter = _build_symbol_filter(symbols, 'v.symbol')

    query = f"""
    WITH latest_snapshots AS (
      SELECT
        symbol,
        last_price,
        pct_change,
        is_stale,
        snapshot_ts,
        ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY snapshot_ts DESC) AS rn
      FROM `{PROJECT_ID}.{DATASET}.sector_snapshots`
      WHERE DATE(snapshot_ts) = CURRENT_DATE()
    )
    SELECT
      v.timestamp,
      v.symbol,
      v.price,
      v.trade_volume,
      v.avg_volume,
      v.spike_ratio,
      m.direction,
      m.pct_change AS momentum_pct,
      m.candles_in_direction,
      CASE
        WHEN m.window_end_ts IS NOT NULL THEN 'CONFIRMED'
        ELSE 'UNCONFIRMED'
      END AS confidence,
      ss.pct_change AS session_pct_change,
      ss.is_stale
    FROM `{PROJECT_ID}.{DATASET}.volume_spikes` v
    LEFT JOIN `{PROJECT_ID}.{DATASET}.momentum_signals` m
      ON v.symbol = m.symbol
      AND DATE(m.window_end_ts) = CURRENT_DATE()
      AND TIMESTAMP_DIFF(m.window_end_ts, v.timestamp, SECOND) BETWEEN -300 AND 300
    LEFT JOIN latest_snapshots ss
      ON v.symbol = ss.symbol
      AND ss.rn = 1
    WHERE DATE(v.timestamp) = CURRENT_DATE()
      AND v.timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {minutes_back} MINUTE)
      {symbols_filter}
    QUALIFY ROW_NUMBER() OVER (
      PARTITION BY v.timestamp, v.symbol
      ORDER BY ABS(TIMESTAMP_DIFF(COALESCE(m.window_end_ts, v.timestamp), v.timestamp, SECOND))
    ) = 1
    ORDER BY v.timestamp DESC
    """

    return client.query(query, job_config=bigquery.QueryJobConfig(use_query_cache=False)).to_dataframe()


def get_market_breadth():
    """Latest pct_change per symbol from sector_snapshots — used for breadth bar"""
    query = f"""
    WITH latest AS (
      SELECT
        symbol,
        pct_change,
        last_price,
        is_stale,
        ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY snapshot_ts DESC) AS rn
      FROM `{PROJECT_ID}.{DATASET}.sector_snapshots`
      WHERE DATE(snapshot_ts) = CURRENT_DATE()
    )
    SELECT symbol, pct_change, last_price, is_stale
    FROM latest
    WHERE rn = 1
    ORDER BY pct_change DESC
    """
    return client.query(query, job_config=bigquery.QueryJobConfig(use_query_cache=False)).to_dataframe()


def get_session_leaderboard():
    """Signal count per symbol for today across all signal types"""
    query = f"""
    SELECT
      symbol,
      COUNTIF(signal_type = 'volume')     AS volume_count,
      COUNTIF(signal_type = 'momentum')   AS momentum_count,
      COUNTIF(signal_type = 'volatility') AS volatility_count,
      COUNT(*) AS total_signals
    FROM (
      SELECT symbol, 'volume'     AS signal_type FROM `{PROJECT_ID}.{DATASET}.volume_spikes`
      WHERE DATE(timestamp) = CURRENT_DATE()

      UNION ALL

      SELECT symbol, 'momentum'   AS signal_type FROM `{PROJECT_ID}.{DATASET}.momentum_signals`
      WHERE DATE(window_end_ts) = CURRENT_DATE()

      UNION ALL

      SELECT symbol, 'volatility' AS signal_type FROM `{PROJECT_ID}.{DATASET}.volatility_spikes`
      WHERE DATE(timestamp) = CURRENT_DATE()
    )
    GROUP BY symbol
    ORDER BY total_signals DESC
    """
    return client.query(query, job_config=bigquery.QueryJobConfig(use_query_cache=False)).to_dataframe()


def get_rvol(date_str: str, symbols: list = None):
    """RVOL: today's signal count vs 30-day historical average by hour"""
    symbols_filter = _build_symbol_filter(symbols)

    query = f"""
    WITH today_vol AS (
      SELECT
        EXTRACT(HOUR FROM timestamp) AS trading_hour,
        COUNT(*) AS signal_count,
        SUM(trade_volume) AS trade_volume_sum
      FROM `{PROJECT_ID}.{DATASET}.volume_spikes`
      WHERE DATE(timestamp) = DATE('{date_str}')
        {symbols_filter}
      GROUP BY trading_hour
    ),
    historical_avg AS (
      SELECT
        trading_hour,
        AVG(daily_count)  AS avg_signal_count,
        AVG(daily_volume) AS avg_trade_volume
      FROM (
        SELECT
          EXTRACT(HOUR FROM timestamp) AS trading_hour,
          COUNT(*)            AS daily_count,
          SUM(trade_volume)   AS daily_volume
        FROM `{PROJECT_ID}.{DATASET}.volume_spikes`
        WHERE DATE(timestamp) BETWEEN DATE_SUB(DATE('{date_str}'), INTERVAL 30 DAY)
                                   AND DATE_SUB(DATE('{date_str}'), INTERVAL 1 DAY)
          {symbols_filter}
        GROUP BY DATE(timestamp), EXTRACT(HOUR FROM timestamp)
      )
      GROUP BY trading_hour
    )
    SELECT
      t.trading_hour,
      t.signal_count                                              AS today_count,
      t.trade_volume_sum                                          AS today_volume,
      ROUND(h.avg_signal_count, 1)                               AS avg_signal_count,
      ROUND(SAFE_DIVIDE(t.signal_count, h.avg_signal_count), 2)  AS rvol_signals,
      ROUND(SAFE_DIVIDE(t.trade_volume_sum, h.avg_trade_volume), 2) AS rvol_volume
    FROM today_vol t
    LEFT JOIN historical_avg h USING (trading_hour)
    ORDER BY trading_hour
    """
    return client.query(query, job_config=bigquery.QueryJobConfig(use_query_cache=False)).to_dataframe()


def get_signal_clusters(minutes_back: int = 60):
    """2-minute buckets where 3+ distinct symbols fired simultaneously"""
    query = f"""
    WITH all_signals AS (
      SELECT timestamp AS event_time, symbol, 'volume' AS signal_type
      FROM `{PROJECT_ID}.{DATASET}.volume_spikes`
      WHERE DATE(timestamp) = CURRENT_DATE()

      UNION ALL

      SELECT window_end_ts AS event_time, symbol, 'momentum' AS signal_type
      FROM `{PROJECT_ID}.{DATASET}.momentum_signals`
      WHERE DATE(window_end_ts) = CURRENT_DATE()

      UNION ALL

      SELECT timestamp AS event_time, symbol, 'volatility' AS signal_type
      FROM `{PROJECT_ID}.{DATASET}.volatility_spikes`
      WHERE DATE(timestamp) = CURRENT_DATE()
    ),
    bucketed AS (
      SELECT
        TIMESTAMP_SECONDS(
          CAST(FLOOR(UNIX_SECONDS(event_time) / 120) * 120 AS INT64)
        ) AS bucket_start,
        symbol,
        signal_type
      FROM all_signals
      WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {minutes_back} MINUTE)
    )
    SELECT
      bucket_start,
      TIMESTAMP_ADD(bucket_start, INTERVAL 120 SECOND)  AS bucket_end,
      COUNT(DISTINCT symbol)                            AS symbols_count,
      STRING_AGG(DISTINCT symbol ORDER BY symbol)       AS symbols_list,
      COUNT(*)                                          AS total_signals,
      COUNTIF(signal_type = 'volume')                   AS volume_count,
      COUNTIF(signal_type = 'momentum')                 AS momentum_count,
      COUNTIF(signal_type = 'volatility')               AS volatility_count
    FROM bucketed
    GROUP BY bucket_start
    HAVING COUNT(DISTINCT symbol) >= 3
    ORDER BY bucket_start DESC
    LIMIT 10
    """
    return client.query(query, job_config=bigquery.QueryJobConfig(use_query_cache=False)).to_dataframe()


def get_opening_range(date_str: str, symbols: list = None):
    """First-30-min high/low + volume spike signals that broke out after the opening range"""
    symbols_filter       = _build_symbol_filter(symbols)
    symbols_filter_v     = _build_symbol_filter(symbols, 'v.symbol')

    query = f"""
    WITH market_open AS (
      SELECT MIN(snapshot_ts) AS open_ts
      FROM `{PROJECT_ID}.{DATASET}.sector_snapshots`
      WHERE DATE(snapshot_ts) = DATE('{date_str}')
    ),
    or_range AS (
      SELECT
        ss.symbol,
        MAX(ss.last_price)                        AS or_high,
        MIN(ss.last_price)                        AS or_low,
        ROUND(MAX(ss.last_price) - MIN(ss.last_price), 2) AS or_size
      FROM `{PROJECT_ID}.{DATASET}.sector_snapshots` ss
      CROSS JOIN market_open mo
      WHERE DATE(ss.snapshot_ts) = DATE('{date_str}')
        AND ss.snapshot_ts BETWEEN mo.open_ts
                               AND TIMESTAMP_ADD(mo.open_ts, INTERVAL 30 MINUTE)
        {symbols_filter}
      GROUP BY ss.symbol
    )
    SELECT
      v.timestamp,
      v.symbol,
      ROUND(v.price, 2)       AS price,
      ROUND(v.spike_ratio, 2) AS spike_ratio,
      orb.or_high,
      orb.or_low,
      orb.or_size,
      CASE
        WHEN v.price > orb.or_high THEN 'BREAKOUT ↑'
        WHEN v.price < orb.or_low  THEN 'BREAKDOWN ↓'
        ELSE 'IN RANGE'
      END AS orb_status,
      ROUND(SAFE_DIVIDE(v.price - orb.or_high, orb.or_high) * 100, 2) AS pct_above_high,
      ROUND(SAFE_DIVIDE(v.price - orb.or_low,  orb.or_low)  * 100, 2) AS pct_above_low
    FROM `{PROJECT_ID}.{DATASET}.volume_spikes` v
    JOIN or_range orb ON v.symbol = orb.symbol
    CROSS JOIN market_open mo
    WHERE DATE(v.timestamp) = DATE('{date_str}')
      AND v.timestamp > TIMESTAMP_ADD(mo.open_ts, INTERVAL 30 MINUTE)
      {symbols_filter_v}
    ORDER BY v.timestamp DESC
    LIMIT 200
    """
    return client.query(query, job_config=bigquery.QueryJobConfig(use_query_cache=False)).to_dataframe()


def get_symbol_win_rates(date_range_days: int = 30, symbols: list = None, min_spike_ratio: float = 1.0):
    """Win rate broken down by symbol"""
    symbols_filter = _build_symbol_filter(symbols)

    query = f"""
    WITH volume_signals AS (
      SELECT timestamp AS signal_time, symbol, price AS entry_price, spike_ratio
      FROM `{PROJECT_ID}.{DATASET}.volume_spikes`
      WHERE DATE(timestamp) >= DATE_SUB(CURRENT_DATE(), INTERVAL {date_range_days} DAY)
        AND spike_ratio >= {min_spike_ratio}
        {symbols_filter}
    ),
    sector_after AS (
      SELECT
        vs.symbol,
        vs.entry_price,
        ss.last_price AS exit_price
      FROM volume_signals vs
      JOIN `{PROJECT_ID}.{DATASET}.sector_snapshots` ss
        ON vs.symbol = ss.symbol
        AND ss.snapshot_ts BETWEEN
            TIMESTAMP_ADD(vs.signal_time, INTERVAL 15 MINUTE)
            AND TIMESTAMP_ADD(vs.signal_time, INTERVAL 60 MINUTE)
        AND DATE(ss.snapshot_ts) >= DATE_SUB(CURRENT_DATE(), INTERVAL {date_range_days} DAY)
    )
    SELECT
      symbol,
      COUNT(*)                                                                          AS total_signals,
      COUNTIF((exit_price - entry_price) / entry_price > 0.005)                        AS profitable_half_pct,
      COUNTIF((exit_price - entry_price) / entry_price > 0.01)                         AS profitable_1pct,
      COUNTIF((exit_price - entry_price) / entry_price > 0.02)                         AS profitable_2pct,
      ROUND(100 * COUNTIF((exit_price - entry_price) / entry_price > 0.01)
            / NULLIF(COUNT(*), 0), 1)                                                  AS win_rate_pct,
      ROUND(AVG((exit_price - entry_price) / entry_price * 100), 3)                   AS avg_return_pct
    FROM sector_after
    GROUP BY symbol
    ORDER BY win_rate_pct DESC
    """
    return client.query(query, job_config=bigquery.QueryJobConfig(use_query_cache=False)).to_dataframe()


def get_per_signal_pnl(date_range_days: int = 30, symbols: list = None):
    """P&L at 5 / 15 / 30 min for each individual volume spike"""
    symbols_filter = _build_symbol_filter(symbols)

    query = f"""
    WITH signals AS (
      SELECT timestamp AS signal_time, symbol, price AS entry_price, spike_ratio
      FROM `{PROJECT_ID}.{DATASET}.volume_spikes`
      WHERE DATE(timestamp) >= DATE_SUB(CURRENT_DATE(), INTERVAL {date_range_days} DAY)
        {symbols_filter}
    ),
    exits AS (
      SELECT
        s.signal_time,
        s.symbol,
        s.entry_price,
        s.spike_ratio,
        MAX(CASE WHEN ss.snapshot_ts BETWEEN TIMESTAMP_ADD(s.signal_time, INTERVAL 4  MINUTE)
                                         AND TIMESTAMP_ADD(s.signal_time, INTERVAL 6  MINUTE)
                 THEN ss.last_price END) AS price_5m,
        MAX(CASE WHEN ss.snapshot_ts BETWEEN TIMESTAMP_ADD(s.signal_time, INTERVAL 13 MINUTE)
                                         AND TIMESTAMP_ADD(s.signal_time, INTERVAL 17 MINUTE)
                 THEN ss.last_price END) AS price_15m,
        MAX(CASE WHEN ss.snapshot_ts BETWEEN TIMESTAMP_ADD(s.signal_time, INTERVAL 28 MINUTE)
                                         AND TIMESTAMP_ADD(s.signal_time, INTERVAL 32 MINUTE)
                 THEN ss.last_price END) AS price_30m
      FROM signals s
      JOIN `{PROJECT_ID}.{DATASET}.sector_snapshots` ss
        ON s.symbol = ss.symbol
        AND ss.snapshot_ts BETWEEN TIMESTAMP_ADD(s.signal_time, INTERVAL 4 MINUTE)
                               AND TIMESTAMP_ADD(s.signal_time, INTERVAL 32 MINUTE)
        AND DATE(ss.snapshot_ts) >= DATE_SUB(CURRENT_DATE(), INTERVAL {date_range_days} DAY)
      GROUP BY s.signal_time, s.symbol, s.entry_price, s.spike_ratio
    )
    SELECT
      signal_time,
      symbol,
      ROUND(entry_price, 2)                                                AS entry_price,
      ROUND(spike_ratio, 2)                                                AS spike_ratio,
      ROUND(price_5m,  2)                                                  AS price_5m,
      ROUND(price_15m, 2)                                                  AS price_15m,
      ROUND(price_30m, 2)                                                  AS price_30m,
      ROUND(SAFE_DIVIDE(price_5m  - entry_price, entry_price) * 100, 2)   AS pnl_5m_pct,
      ROUND(SAFE_DIVIDE(price_15m - entry_price, entry_price) * 100, 2)   AS pnl_15m_pct,
      ROUND(SAFE_DIVIDE(price_30m - entry_price, entry_price) * 100, 2)   AS pnl_30m_pct
    FROM exits
    WHERE price_15m IS NOT NULL
    ORDER BY signal_time DESC
    LIMIT 200
    """
    return client.query(query, job_config=bigquery.QueryJobConfig(use_query_cache=False)).to_dataframe()


def get_all_realtime_signals(minutes_back: int = 10, symbols: list = None):
    """All signal types (volume, momentum, volatility) from the last N minutes"""
    symbols_filter = _build_symbol_filter(symbols, 'v.symbol')
    symbols_filter_plain = _build_symbol_filter(symbols)

    query = f"""
    WITH latest_snapshots AS (
      SELECT
        symbol, last_price, pct_change, is_stale,
        ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY snapshot_ts DESC) AS rn
      FROM `{PROJECT_ID}.{DATASET}.sector_snapshots`
      WHERE DATE(snapshot_ts) = CURRENT_DATE()
    ),
    volume_signals AS (
      SELECT
        v.timestamp          AS event_time,
        v.symbol,
        'volume'             AS signal_type,
        v.price,
        v.spike_ratio        AS strength,
        m.direction,
        CAST(NULL AS FLOAT64) AS extra_metric,
        CASE WHEN m.window_end_ts IS NOT NULL THEN 'CONFIRMED' ELSE 'UNCONFIRMED' END AS confirmation
      FROM `{PROJECT_ID}.{DATASET}.volume_spikes` v
      LEFT JOIN `{PROJECT_ID}.{DATASET}.momentum_signals` m
        ON v.symbol = m.symbol
        AND DATE(m.window_end_ts) = CURRENT_DATE()
        AND TIMESTAMP_DIFF(m.window_end_ts, v.timestamp, SECOND) BETWEEN -300 AND 300
      WHERE DATE(v.timestamp) = CURRENT_DATE()
        AND v.timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {minutes_back} MINUTE)
        {symbols_filter}
      QUALIFY ROW_NUMBER() OVER (
        PARTITION BY v.timestamp, v.symbol
        ORDER BY ABS(TIMESTAMP_DIFF(COALESCE(m.window_end_ts, v.timestamp), v.timestamp, SECOND))
      ) = 1
    ),
    all_signals AS (
      SELECT event_time, symbol, signal_type, price, strength, direction, extra_metric, confirmation
      FROM volume_signals

      UNION ALL

      SELECT
        window_end_ts               AS event_time,
        symbol,
        'momentum'                  AS signal_type,
        latest_close                AS price,
        ABS(pct_change)             AS strength,
        direction,
        CAST(candles_in_direction AS FLOAT64) AS extra_metric,
        CAST(NULL AS STRING)        AS confirmation
      FROM `{PROJECT_ID}.{DATASET}.momentum_signals`
      WHERE DATE(window_end_ts) = CURRENT_DATE()
        AND window_end_ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {minutes_back} MINUTE)
        {symbols_filter_plain}

      UNION ALL

      SELECT
        timestamp                   AS event_time,
        symbol,
        'volatility'                AS signal_type,
        price,
        z_score                     AS strength,
        CAST(NULL AS STRING)        AS direction,
        std_dev                     AS extra_metric,
        CAST(NULL AS STRING)        AS confirmation
      FROM `{PROJECT_ID}.{DATASET}.volatility_spikes`
      WHERE DATE(timestamp) = CURRENT_DATE()
        AND timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {minutes_back} MINUTE)
        {symbols_filter_plain}
    )
    SELECT
      a.event_time                        AS timestamp,
      a.symbol,
      a.signal_type,
      COALESCE(a.price, ss.last_price)    AS price,
      a.strength,
      a.direction,
      a.extra_metric,
      a.confirmation,
      ss.pct_change                       AS session_pct_change,
      ss.is_stale
    FROM all_signals a
    LEFT JOIN latest_snapshots ss ON a.symbol = ss.symbol AND ss.rn = 1
    ORDER BY a.event_time DESC
    LIMIT 100
    """
    return client.query(query, job_config=bigquery.QueryJobConfig(use_query_cache=False)).to_dataframe()


def get_all_symbols():
    """Get all 10 symbols tracked by the system"""
    return ['AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'META', 'TSLA', 'AMD', 'AVGO', 'PLTR']
