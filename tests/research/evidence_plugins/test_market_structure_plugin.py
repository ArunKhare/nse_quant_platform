"""Tests for look-ahead-safe market-structure evidence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from nse_quant.core.settings import MarketStructureSettings
from nse_quant.research.evidence_plugins.base import DecisionContext
from nse_quant.research.evidence_plugins.market_structure import (
    MarketStructurePlugin,
)
from nse_quant.research.evidence_plugins.registry import (
    EvidencePluginRunner,
)

DECISION_TS = datetime(2026, 10, 31, 10, 0, tzinfo=UTC)


class FakeResult:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self._rows = rows

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self._rows


class FakeConnection:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self._rows = rows
        self.queries: list[tuple[str, list[Any]]] = []

    def execute(self, query: str, params: list[Any]) -> FakeResult:
        self.queries.append((query, params))

        token, as_of, limit = params

        filtered = [row for row in self._rows if row[0] <= as_of]

        return FakeResult(filtered[-limit:])


class FakeStore:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self.conn = FakeConnection(rows)


def build_context(
    decision_ts: datetime | None = None,
) -> DecisionContext:
    return DecisionContext(
        run_id="run-1",
        symbol="NIFTY",
        ts=decision_ts or DECISION_TS,
        features={},
        snapshot={},
        iv_history_count=30,
        current_regime="RANGE",
        effective_regimes=[],
        regime_policy=None,
        spot_instrument_token=256265,
    )


def candle_row(
    minute_offset: int = 0,
    *,
    high: float,
    low: float,
    close: float,
    ts: datetime | None = None,
) -> tuple[Any, ...]:
    candle_ts = ts if ts is not None else DECISION_TS - timedelta(minutes=minute_offset)

    return (
        candle_ts,
        close,
        high,
        low,
        close,
        1000,
    )


def build_plugin(
    rows: list[tuple[Any, ...]],
    *,
    settings: MarketStructureSettings | None = None,
    decision_ts: datetime | None = None,
) -> tuple[MarketStructurePlugin, FakeStore]:
    store = FakeStore(rows)
    plugin = MarketStructurePlugin(
        store=store,
        settings=settings or MarketStructureSettings(),
    )
    return plugin, store


def test_no_history_is_incomplete() -> None:
    plugin, _ = build_plugin([])

    result = plugin.build(build_context())

    assert result["available"] is True
    assert result["complete"] is False
    assert result["bars_used"] == 0
    assert result["timeframes"] == {}
    assert result["reason"] == "no_1m_history"


def test_insufficient_history_has_no_structure() -> None:
    rows = [
        candle_row(
            minute_offset=15 - index,
            high=100 + index,
            low=99 + index,
            close=100 + index,
        )
        for index in range(15)
    ]

    plugin, _ = build_plugin(rows)

    result = plugin.build(build_context())
    timeframe = result["timeframes"]["15m"]

    assert result["complete"] is False
    assert timeframe["market_structure"] is None
    assert timeframe["available_bars"] == 0


def test_higher_highs_and_lows_are_detected() -> None:
    highs = [10, 11, 15, 12, 13, 16, 14, 15, 17]
    lows = [8, 7, 6, 4, 6, 7, 5, 8, 9]

    rows = [
        candle_row(
            minute_offset=10 - index,
            high=highs[index],
            low=lows[index],
            close=highs[index],
        )
        for index in range(len(highs))
    ]
    rows.append(
        candle_row(
            minute_offset=1,
            high=18,
            low=10,
            close=18,
        )
    )

    plugin, _ = build_plugin(
        rows,
        settings=MarketStructureSettings(
            timeframes=["1m"],
            swing_lookback=2,
        ),
    )

    result = plugin.build(build_context())
    timeframe = result["timeframes"]["1m"]

    assert result["complete"] is True
    assert timeframe["market_structure"] == "HH_HL"


def test_bullish_bos_is_detected() -> None:
    highs = [10, 11, 15, 12, 13, 16, 14, 15, 17]
    lows = [8, 7, 6, 4, 6, 7, 5, 8, 9]

    rows = [
        candle_row(
            minute_offset=10 - index,
            high=highs[index],
            low=lows[index],
            close=highs[index],
        )
        for index in range(len(highs))
    ]

    rows.append(
        candle_row(
            minute_offset=1,
            high=18,
            low=10,
            close=18,
        )
    )

    plugin, _ = build_plugin(
        rows,
        settings=MarketStructureSettings(
            timeframes=["1m"],
            swing_lookback=2,
        ),
    )

    result = plugin.build(build_context())
    timeframe = result["timeframes"]["1m"]

    assert timeframe["bos"] == "BULLISH_BOS"


def test_future_candles_are_excluded() -> None:
    rows = [
        candle_row(
            minute_offset=15 - index,
            high=100 + index,
            low=99 + index,
            close=100 + index,
        )
        for index in range(15)
    ]

    rows.append(
        (
            DECISION_TS + timedelta(minutes=1),
            100.0,
            110.0,
            99.0,
            110.0,
            1000,
        )
    )

    plugin, store = build_plugin(rows)

    result = plugin.build(build_context())

    assert result["bars_used"] == 15

    _query, params = store.conn.queries[0]
    assert params[1] == DECISION_TS


def test_plugin_error_is_contained_by_runner() -> None:
    class FailingConnection:
        def execute(self, *_args: Any, **_kwargs: Any) -> Any:
            raise RuntimeError("database unavailable")

    class FailingStore:
        conn = FailingConnection()

    plugin = MarketStructurePlugin(
        store=FailingStore(),
        settings=MarketStructureSettings(enabled=True),
    )

    results = EvidencePluginRunner([plugin]).run(build_context())

    assert len(results) == 1
    assert results[0].plugin == "market_structure"
    assert results[0].available is False
    assert results[0].complete is False
    assert results[0].payload["available"] is False
    assert results[0].payload["error_type"] == "RuntimeError"


@pytest.mark.parametrize(
    "timeframe",
    ["2m", "invalid"],
)
def test_unsupported_timeframe_raises_value_error(
    timeframe: str,
) -> None:
    plugin, _ = build_plugin(
        [
            candle_row(
                minute_offset=15 - index,
                high=100 + index,
                low=99 + index,
                close=100 + index,
            )
            for index in range(15)
        ],
        settings=MarketStructureSettings(
            timeframes=[timeframe],
        ),
    )

    with pytest.raises(ValueError, match="Unsupported timeframe"):
        plugin.build(build_context())


def test_15m_structure_uses_completed_buckets() -> None:
    decision_ts = datetime(2024, 1, 2, 9, 45, tzinfo=UTC)

    rows = [
        candle_row(
            ts=decision_ts.replace(minute=15) + timedelta(minutes=index),
            high=110,
            low=90,
            close=100,
        )
        for index in range(30)
    ]

    settings = MarketStructureSettings(
        timeframes=["15m"],
        swing_lookback=2,
    )

    baseline_plugin, _ = build_plugin(rows, settings=settings)
    baseline = baseline_plugin.build(build_context(decision_ts=decision_ts))

    # Without a later input bucket, 09:30 is treated as active.
    assert baseline["timeframes"]["15m"]["available_bars"] == 1

    rows.append(
        candle_row(
            ts=decision_ts,
            high=10_000,
            low=1,
            close=5_000,
        )
    )

    plugin, store = build_plugin(rows, settings=settings)
    result = plugin.build(build_context(decision_ts=decision_ts))
    timeframe = result["timeframes"]["15m"]

    assert result["bars_used"] == 31
    assert timeframe["available_bars"] == 2
    assert timeframe["opening_range"] is not None
    assert timeframe["opening_range"]["high"] == 110
    assert timeframe["opening_range"]["low"] == 90

    _query, params = store.conn.queries[0]
    assert params[1] == decision_ts
