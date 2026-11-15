"""Tests for equity candle capture."""

from __future__ import annotations

from nse_quant.market_data.equity_candles import (
    EQUITY_WATCHLIST,
    read_equity_candles,
    write_equity_candles,
)


def test_watchlist_has_10_symbols():
    assert len(EQUITY_WATCHLIST) == 10
    assert "RELIANCE" in EQUITY_WATCHLIST
    assert "SUNPHARMA" in EQUITY_WATCHLIST


def test_write_and_read_equity_candles(tmp_path):
    from nse_quant.persistence.duckdb_store import DuckDBStore

    store = DuckDBStore(path=tmp_path / "test.duckdb")
    try:
        candles = [
            {
                "date": "2026-01-02",
                "open": 100.0,
                "high": 105.0,
                "low": 99.0,
                "close": 104.0,
                "volume": 1000000,
            },
            {
                "date": "2026-01-03",
                "open": 104.0,
                "high": 108.0,
                "low": 103.0,
                "close": 107.0,
                "volume": 1200000,
            },
        ]
        count = write_equity_candles(store, symbol="RELIANCE", candles=candles, instrument_token=12345)
        assert count == 2
        frame = read_equity_candles(store, symbol="RELIANCE")
        assert len(frame) == 2
        assert frame.iloc[0]["close"] == 104.0
        assert frame.iloc[1]["close"] == 107.0
    finally:
        store.close()
