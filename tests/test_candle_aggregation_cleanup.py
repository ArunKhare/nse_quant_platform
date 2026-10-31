"""Temporary-DuckDB and CLI regression tests for the aggregation extraction."""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import duckdb
import pytest

from nse_quant.market_data import candle_aggregation as aggregation

ROOT = Path(__file__).resolve().parents[1]
DAY = "2026-10-30"


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def store():
    conn = duckdb.connect(":memory:")
    conn.execute("SET TimeZone = 'UTC'")
    conn.execute(
        """
        CREATE TABLE spot_candles (
            symbol VARCHAR, instrument_token BIGINT, ts TIMESTAMPTZ,
            interval VARCHAR, open DOUBLE, high DOUBLE, low DOUBLE,
            close DOUBLE, volume BIGINT, oi BIGINT
        )
        """
    )
    try:
        yield SimpleNamespace(conn=conn)
    finally:
        conn.close()


def insert(store, *, symbol="NIFTY", token=1, day=30, minute=0, interval="1m"):
    store.conn.execute(
        "INSERT INTO spot_candles VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            symbol,
            token,
            datetime(2026, 10, day, 9, minute, tzinfo=UTC),
            interval,
            100 + minute,
            104 + minute,
            98 + minute,
            102 + minute,
            10 + minute,
            20 + minute,
        ],
    )


def rows(store, interval):
    return store.conn.execute(
        """
        SELECT * FROM spot_candles WHERE interval = ?
        ORDER BY symbol, instrument_token, ts
        """,
        [interval],
    ).fetchall()


@pytest.mark.parametrize("interval,minutes", [("5m", 5), ("15m", 15), ("30m", 30), ("60m", 60)])
def test_intraday_values_buckets_instruments_and_repeat(store, interval, minutes):
    for minute in (0, 1, 6):
        insert(store, minute=minute)
    insert(store, token=2)
    insert(store, symbol="BANKNIFTY", token=3, interval=interval)
    insert(store, day=29, interval=interval)
    before_other = store.conn.execute(
        "SELECT * FROM spot_candles WHERE symbol = 'BANKNIFTY' OR CAST(ts AS DATE) = '2026-10-29'"
    ).fetchall()
    expected_count = 3 if interval == "5m" else 2
    for _ in range(2):
        assert (
            aggregation.build_interval_candles(
                store=store,
                symbol="NIFTY",
                trade_date=DAY,
                interval=interval,
            )
            == expected_count
        )
    actual = store.conn.execute(
        """
        SELECT instrument_token, ts, open, high, low, close, volume, oi
        FROM spot_candles WHERE symbol = 'NIFTY' AND interval = ?
          AND CAST(ts AS DATE) = ? ORDER BY instrument_token, ts
        """,
        [interval, DAY],
    ).fetchall()
    if minutes == 5:
        assert actual[0] == (1, datetime(2026, 10, 30, 9, tzinfo=UTC), 100, 105, 98, 103, 21, 21)
        assert actual[1] == (
            1,
            datetime(2026, 10, 30, 9, 5, tzinfo=UTC),
            106,
            110,
            104,
            108,
            16,
            26,
        )
    else:
        assert actual[0] == (1, datetime(2026, 10, 30, 9, tzinfo=UTC), 100, 110, 98, 108, 37, 26)
    assert actual[-1][0] == 2
    assert (
        store.conn.execute(
            "SELECT * FROM spot_candles  \
            WHERE symbol = 'BANKNIFTY' OR CAST(ts AS DATE) = '2026-10-29'"
        ).fetchall()
        == before_other
    )


def test_daily_values_multiple_instruments_replacement_and_repeat(store):
    for minute in (0, 1, 6):
        insert(store, minute=minute)
    insert(store, token=2)
    insert(store, interval="day", token=99)
    insert(store, day=29, interval="day")
    for _ in range(2):
        assert (
            aggregation.build_daily_candles(
                store=store,
                symbol="NIFTY",
                start_date=DAY,
                end_date=DAY,
            )
            == 0
        )
    result = rows(store, "day")
    current = [row for row in result if row[2].day == 30]
    assert len(current) == 2
    assert current[0] == (
        "NIFTY",
        1,
        datetime(2026, 10, 30, tzinfo=UTC),
        "day",
        100,
        110,
        98,
        108,
        37,
        26,
    )
    assert current[1][1] == 2
    assert len(result) == 3


def test_legacy_daily_missing_source_deletes_target_then_fails(store):
    insert(store, interval="day")
    assert (
        aggregation.build_daily_candles(
            store=store,
            symbol="NIFTY",
            start_date=DAY,
            end_date=DAY,
        )
        == 1
    )
    assert rows(store, "day") == []


def test_daily_empty_range_with_source_elsewhere_succeeds(store):
    insert(store, day=29)
    insert(store, interval="day")
    assert (
        aggregation.build_daily_candles(
            store=store,
            symbol="NIFTY",
            start_date=DAY,
            end_date=DAY,
        )
        == 0
    )
    assert rows(store, "day") == []


def test_intraday_missing_source_deletes_target_and_returns_zero(store):
    insert(store, interval="5m")
    assert (
        aggregation.build_interval_candles(
            store=store,
            symbol="NIFTY",
            trade_date=DAY,
            interval="5m",
        )
        == 0
    )
    assert rows(store, "5m") == []


def test_invalid_interval_does_not_mutate(store):
    insert(store, interval="5m")
    before = rows(store, "5m")
    with pytest.raises(ValueError, match="Unsupported interval"):
        aggregation.build_interval_candles(
            store=store,
            symbol="NIFTY",
            trade_date=DAY,
            interval="2m",
        )
    assert rows(store, "5m") == before


@pytest.mark.parametrize(
    "argv",
    [
        ["aggregate-daily", "--start-date", "2026-10-31", "--end-date", DAY],
        ["aggregate-intraday", "--trade-date", DAY, "--intervals", "2m"],
        ["aggregate-intraday", "--trade-date", DAY, "--intervals", ""],
        ["aggregate-intraday", "--trade-date", "not-a-date"],
    ],
)
def test_cli_rejects_invalid_input_before_opening_store(monkeypatch, argv):
    module = load_script("manage_candles")
    factory = MagicMock()
    monkeypatch.setattr(module, "DuckDBStore", factory)
    with pytest.raises(SystemExit) as error:
        module.main(argv)
    assert error.value.code == 2
    factory.assert_not_called()


@pytest.mark.parametrize(
    "script,argv,function,result,expected",
    [
        (
            "manage_candles",
            ["aggregate-daily", "--start-date", DAY, "--end-date", DAY],
            "build_daily_candles",
            1,
            1,
        ),
        (
            "manage_candles",
            ["aggregate-intraday", "--trade-date", DAY, "--intervals", "5m"],
            "build_interval_candles",
            3,
            0,
        ),
    ],
)
def test_cli_forwarding_close_and_failures(monkeypatch, script, argv, function, result, expected):
    module = load_script(script)
    store = MagicMock()
    monkeypatch.setattr(module, "DuckDBStore", lambda: store)
    operation = MagicMock(return_value=result)
    monkeypatch.setattr(module, function, operation)
    assert module.main([*argv, "--symbol", "BANKNIFTY"]) == expected
    assert operation.call_args.kwargs["symbol"] == "BANKNIFTY"
    assert operation.call_args.kwargs["store"] is store
    if function == "build_daily_candles":
        assert operation.call_args.kwargs["start_date"] == DAY
        assert operation.call_args.kwargs["end_date"] == DAY
    else:
        assert operation.call_args.kwargs["trade_date"] == DAY
        assert operation.call_args.kwargs["interval"] == "5m"
    store.conn.close.assert_called_once()
    store.conn.close.reset_mock()
    operation.side_effect = RuntimeError("aggregation failed")
    with pytest.raises(RuntimeError, match="aggregation failed"):
        module.main(argv)
    store.conn.close.assert_called_once()
