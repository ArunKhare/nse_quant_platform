"""Aggregate persisted one-minute candles without owning the store lifecycle.

This extraction preserves legacy SQL, including date/time bucket semantics and
replacement ordering. Transaction and missing-source protections are out of scope.
"""

from __future__ import annotations

from nse_quant.persistence.duckdb_store import DuckDBStore

INTERVALS = {
    "5m": "5 minutes",
    "15m": "15 minutes",
    "30m": "30 minutes",
    "60m": "60 minutes",
}


def build_interval_candles(
    *,
    store: DuckDBStore,
    symbol: str,
    trade_date: str,
    interval: str,
) -> int:
    """Replace a single intraday interval/date and return the resulting row count."""
    if interval not in INTERVALS:
        raise ValueError(
            f"Unsupported interval: {interval}. Supported intervals: {', '.join(INTERVALS)}",
        )

    bucket = INTERVALS[interval]
    store.conn.execute(
        """
        DELETE FROM spot_candles
        WHERE symbol = ? AND interval = ? AND CAST(ts AS DATE) = ?
        """,
        [symbol, interval, trade_date],
    )
    store.conn.execute(
        f"""
        INSERT INTO spot_candles (
            symbol, instrument_token, ts, interval,
            open, high, low, close, volume, oi
        )
        SELECT symbol, instrument_token,
               time_bucket(INTERVAL '{bucket}', ts) AS ts,
               ? AS interval,
               arg_min(open, ts) AS open,
               max(high) AS high,
               min(low) AS low,
               arg_max(close, ts) AS close,
               COALESCE(sum(volume), 0) AS volume,
               arg_max(oi, ts) AS oi
        FROM spot_candles
        WHERE symbol = ? AND interval = '1m' AND CAST(ts AS DATE) = ?
        GROUP BY symbol, instrument_token,
                 time_bucket(INTERVAL '{bucket}', ts)
        """,  # noqa: S608
        [interval, symbol, trade_date],
    )
    count = store.conn.execute(
        """
        SELECT COUNT(*) FROM spot_candles
        WHERE symbol = ? AND interval = ? AND CAST(ts AS DATE) = ?
        """,
        [symbol, interval, trade_date],
    ).fetchone()[0]
    return int(count)


def build_daily_candles(
    *,
    store: DuckDBStore,
    symbol: str,
    start_date: str,
    end_date: str,
) -> int:
    """Return legacy CLI status: 1 if the symbol has no 1m source, else 0.

    The legacy source-presence check is symbol-wide, not restricted to the range.
    An empty requested range can therefore succeed with zero generated rows.
    """
    store.conn.execute(
        """
        DELETE FROM spot_candles
        WHERE symbol = ? AND interval = 'day'
          AND CAST(ts AS DATE) BETWEEN ? AND ?
        """,
        [symbol, start_date, end_date],
    )
    instrument_token = store.conn.execute(
        """
        SELECT instrument_token FROM spot_candles
        WHERE symbol = ? AND interval = '1m'
        ORDER BY ts DESC LIMIT 1
        """,
        [symbol],
    ).fetchone()
    if instrument_token is None:
        print(f"No 1-minute candles found for {symbol}")
        return 1

    store.conn.execute(
        """
        INSERT INTO spot_candles (
            symbol, instrument_token, ts, interval,
            open, high, low, close, volume, oi
        )
        SELECT symbol, instrument_token, date_trunc('day', ts) AS ts,
               'day' AS interval,
               arg_min(open, ts) AS open,
               max(high) AS high,
               min(low) AS low,
               arg_max(close, ts) AS close,
               COALESCE(sum(volume), 0) AS volume,
               arg_max(oi, ts) AS oi
        FROM spot_candles
        WHERE symbol = ? AND interval = '1m'
          AND CAST(ts AS DATE) BETWEEN ? AND ?
        GROUP BY symbol, instrument_token, date_trunc('day', ts)
        """,
        [symbol, start_date, end_date],
    )
    count_row = store.conn.execute(
        """
        SELECT COUNT(*) FROM spot_candles
        WHERE symbol = ? AND interval = 'day'
          AND CAST(ts AS DATE) BETWEEN ? AND ?
        """,
        [symbol, start_date, end_date],
    ).fetchone()
    count = count_row[0] if count_row is not None else 0
    print(f"{symbol}: built {count} daily candles from 1m data between {start_date} and {end_date}")
    return 0
