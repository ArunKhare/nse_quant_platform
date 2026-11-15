"""Equity candle capture; research-only, no execution authority.

Captures daily equity candles for the cash-stock watchlist and persists them
to the DuckDB store. Reuses the existing spot_candles table with a new
instrument_type column to distinguish equity from index candles.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from nse_quant.persistence.duckdb_store import DuckDBStore

EQUITY_WATCHLIST = [
    "RELIANCE",
    "HDFCBANK",
    "ICICIBANK",
    "INFY",
    "TCS",
    "SBIN",
    "AXISBANK",
    "TATAMOTORS",
    "MARUTI",
    "SUNPHARMA",
]


def ensure_equity_candle_schema(store: DuckDBStore) -> None:
    """Add instrument_type column to spot_candles if missing."""
    columns = {row[1] for row in store.conn.execute("PRAGMA table_info('spot_candles')").fetchall()}
    if "instrument_type" not in columns:
        store.conn.execute("ALTER TABLE spot_candles ADD COLUMN instrument_type VARCHAR DEFAULT 'index'")


def write_equity_candles(
    store: DuckDBStore,
    *,
    symbol: str,
    candles: list[dict[str, Any]],
    instrument_token: int,
) -> int:
    """Write daily equity candles for one symbol."""
    ensure_equity_candle_schema(store)
    for candle in candles:
        store.conn.execute(
            """
            INSERT OR REPLACE INTO spot_candles (
                instrument_token, symbol, interval, ts,
                open, high, low, close, volume, oi, instrument_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                instrument_token,
                symbol,
                "1d",
                candle["date"],
                candle["open"],
                candle["high"],
                candle["low"],
                candle["close"],
                candle["volume"],
                candle.get("oi"),
                "equity",
            ],
        )
    return len(candles)


def read_equity_candles(
    store: DuckDBStore,
    *,
    symbol: str,
    from_date: str | None = None,
    to_date: str | None = None,
) -> pd.DataFrame:
    """Read daily equity candles for one symbol."""
    query = """
        SELECT symbol, ts, open, high, low, close, volume
        FROM spot_candles
        WHERE symbol = ? AND interval = '1d' AND instrument_type = 'equity'
    """
    params: list[Any] = [symbol]
    if from_date:
        query += " AND ts >= ?"
        params.append(from_date)
    if to_date:
        query += " AND ts <= ?"
        params.append(to_date)
    query += " ORDER BY ts"
    return store.conn.execute(query, params).fetchdf()
