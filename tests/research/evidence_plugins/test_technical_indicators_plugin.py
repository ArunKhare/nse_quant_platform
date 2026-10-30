"""Tests for look-ahead-safe technical-indicator evidence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from nse_quant.core.settings import TechnicalIndicatorSettings
from nse_quant.research.evidence_plugins.base import DecisionContext
from nse_quant.research.evidence_plugins.registry import (
    EvidencePluginRunner,
)
from nse_quant.research.evidence_plugins.technical_indicators import (
    TechnicalIndicatorsPlugin,
)

DECISION_TS = datetime(2026, 10, 30, 10, 0, tzinfo=UTC)


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


def build_context() -> DecisionContext:
    return DecisionContext(
        run_id="run-1",
        symbol="NIFTY",
        ts=DECISION_TS,
        features={},
        snapshot={},
        iv_history_count=30,
        current_regime="RANGE",
        effective_regimes=[],
        regime_policy=None,
        spot_instrument_token=256265,
    )


def candle_row(
    minute: int,
    close: float,
) -> tuple[Any, ...]:
    ts = DECISION_TS - timedelta(minutes=minute)
    return (
        ts,
        close,
        close + 1,
        close - 1,
        close,
        1000,
    )


def ascending_rows(count: int = 250) -> list[tuple[Any, ...]]:
    return [
        candle_row(
            minute=count - index,
            close=100 + index * 0.1,
        )
        for index in range(count)
    ]


def build_plugin(
    rows: list[tuple[Any, ...]],
    *,
    settings: TechnicalIndicatorSettings | None = None,
) -> tuple[TechnicalIndicatorsPlugin, FakeStore]:
    store = FakeStore(rows)
    plugin = TechnicalIndicatorsPlugin(
        store=store,
        settings=settings or TechnicalIndicatorSettings(),
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


def test_insufficient_history_returns_none_indicators() -> None:
    rows = ascending_rows(count=10)
    plugin, _ = build_plugin(rows)

    result = plugin.build(build_context())

    timeframe = result["timeframes"]["1m"]

    assert result["complete"] is False
    assert timeframe["rsi"] is None
    assert timeframe["macd"] is None
    assert timeframe["ema"]["ema200"] is None
    assert timeframe["available_bars"] == 9


def test_sufficient_history_computes_core_indicators() -> None:
    rows = ascending_rows(count=250)
    plugin, _ = build_plugin(rows)

    result = plugin.build(build_context())
    timeframe = result["timeframes"]["1m"]

    assert result["available"] is True
    assert timeframe["rsi"] is not None
    assert 0 <= timeframe["rsi"] <= 100

    assert timeframe["macd"] is not None
    assert timeframe["macd"]["macd"] is not None
    assert timeframe["macd"]["signal"] is not None
    assert timeframe["macd"]["histogram"] is not None

    assert timeframe["ema"]["ema9"] is not None
    assert timeframe["ema"]["ema20"] is not None
    assert timeframe["ema"]["ema50"] is not None
    assert timeframe["ema"]["ema200"] is not None

    assert timeframe["ema_alignment"] == "BULLISH"
    assert timeframe["atr_normalized_momentum"] > 0


def test_future_candles_are_excluded() -> None:
    rows = ascending_rows(count=250)
    rows.append(
        (
            DECISION_TS + timedelta(minutes=1),
            999.0,
            1000.0,
            998.0,
            999.0,
            1000,
        )
    )

    plugin, store = build_plugin(rows)
    result = plugin.build(build_context())

    assert result["bars_used"] == 250

    _query, params = store.conn.queries[0]
    assert params[1] == DECISION_TS


def test_plugin_error_is_contained_by_runner() -> None:
    class FailingConnection:
        def execute(self, *_args: Any, **_kwargs: Any) -> Any:
            raise RuntimeError("database unavailable")

    class FailingStore:
        conn = FailingConnection()

    plugin = TechnicalIndicatorsPlugin(
        store=FailingStore(),
        settings=TechnicalIndicatorSettings(enabled=True),
    )

    results = EvidencePluginRunner([plugin]).run(build_context())

    assert len(results) == 1
    assert results[0].plugin == "technical_indicators"
    assert results[0].available is False
    assert results[0].complete is False
    assert results[0].payload["available"] is False
    assert results[0].payload["error"] == "database unavailable"
    assert results[0].payload["error_type"] == "RuntimeError"


@pytest.mark.parametrize(
    "timeframe",
    ["2m", "invalid"],
)
def test_unsupported_timeframe_raises_value_error(
    timeframe: str,
) -> None:
    plugin, _ = build_plugin(
        ascending_rows(),
        settings=TechnicalIndicatorSettings(
            timeframes=[timeframe],
        ),
    )

    with pytest.raises(ValueError, match="Unsupported timeframe"):
        plugin.build(build_context())
