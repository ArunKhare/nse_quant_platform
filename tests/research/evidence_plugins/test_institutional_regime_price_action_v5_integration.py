from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from nse_quant.core.settings import InstitutionalRegimeSettings
from nse_quant.persistence.duckdb_store import DuckDBStore
from nse_quant.research.evidence_plugins.institutional_regime import (
    InstitutionalRegimePlugin,
)


def _trading_dates(count: int, end: date) -> list[date]:
    values: list[date] = []
    current = end - timedelta(days=1)
    while len(values) < count:
        if current.weekday() < 5:
            values.append(current)
        current -= timedelta(days=1)
    return list(reversed(values))


def _insert_daily_bars(store: DuckDBStore, dates: list[date]) -> None:
    previous = 100.0
    for index, trade_date in enumerate(dates):
        close = 100.0 + index * 0.5
        store.conn.execute(
            """
            INSERT INTO spot_candles (
                symbol, instrument_token, ts, interval,
                open, high, low, close, volume, oi
            ) VALUES (?, ?, ?, 'day', ?, ?, ?, ?, ?, ?)
            """,
            [
                "NIFTY",
                256265,
                datetime.combine(trade_date, datetime.min.time(), tzinfo=UTC),
                previous,
                max(previous, close) + 1.0,
                min(previous, close) - 1.0,
                close,
                100_000,
                0,
            ],
        )
        previous = close


def test_price_action_reads_only_completed_daily_bars_and_excludes_current_date(
    tmp_path: Path,
) -> None:
    store = DuckDBStore(tmp_path / "price_action_v5.duckdb")
    try:
        as_of = datetime(2026, 10, 31, 10, 0, tzinfo=UTC)
        local_trade_date = date(2026, 10, 31)
        dates = _trading_dates(280, local_trade_date)
        _insert_daily_bars(store, dates)

        # A current-date daily row must be excluded even if present in storage.
        _insert_daily_bars(store, [local_trade_date])

        # A large 1-minute candle is not eligible input to the daily classifier.
        store.conn.execute(
            """
            INSERT INTO spot_candles (
                symbol, instrument_token, ts, interval,
                open, high, low, close, volume, oi
            ) VALUES (?, ?, ?, '1m', ?, ?, ?, ?, ?, ?)
            """,
            ["NIFTY", 256265, as_of, 100.0, 10_000.0, 1.0, 9_000.0, 1_000_000, 0],
        )

        plugin = InstitutionalRegimePlugin(
            store=store,
            settings=InstitutionalRegimeSettings(
                price_action_daily_history_limit=300,
                price_action_minimum_daily_bars=267,
            ),
        )
        result = plugin._price_action(
            type(
                "DecisionContextStub",
                (),
                {"ts": as_of, "spot_instrument_token": 256265},
            )()
        )

        assert result["available"] is True
        assert result["state"] == "STRONG_BULL_TREND"
        assert result["source"] == "spot_candles.day"
        assert result["bar_completion_policy"] == "exclude_current_ist_calendar_date"
        assert result["latest_bar_date"] == dates[-1].isoformat()
        assert result["latest_bar_date"] < local_trade_date.isoformat()
        assert result["decision_eligibility_asserted"] is False
    finally:
        store.close()


def test_intraday_only_history_does_not_satisfy_daily_classifier(tmp_path: Path) -> None:
    store = DuckDBStore(tmp_path / "price_action_v5_empty.duckdb")
    try:
        as_of = datetime(2026, 10, 31, 10, 0, tzinfo=UTC)
        store.conn.execute(
            """
            INSERT INTO spot_candles (
                symbol, instrument_token, ts, interval,
                open, high, low, close, volume, oi
            ) VALUES (?, ?, ?, '1m', ?, ?, ?, ?, ?, ?)
            """,
            ["NIFTY", 256265, as_of - timedelta(minutes=1), 100.0, 101.0, 99.0, 100.5, 1000, 0],
        )
        plugin = InstitutionalRegimePlugin(
            store=store,
            settings=InstitutionalRegimeSettings(),
        )

        result = plugin._price_action(
            type(
                "DecisionContextStub",
                (),
                {"ts": as_of, "spot_instrument_token": 256265},
            )()
        )

        assert result["available"] is False
        assert result["reason"] == "no_completed_daily_history"
    finally:
        store.close()
