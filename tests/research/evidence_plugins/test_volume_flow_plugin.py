"""Tests for look-ahead-safe volume-flow evidence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from nse_quant.core.settings import VolumeFlowSettings
from nse_quant.research.evidence_plugins.base import DecisionContext
from nse_quant.research.evidence_plugins.registry import (
    EvidencePluginRunner,
)
from nse_quant.research.evidence_plugins.volume_flow import (
    VolumeFlowPlugin,
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
    minute_offset: int,
    volume: float,
) -> tuple[Any, ...]:
    ts = DECISION_TS - timedelta(minutes=minute_offset)

    return (
        ts,
        100.0,
        101.0,
        99.0,
        100.0,
        volume,
    )


def volume_rows(
    count: int,
    volume: float,
) -> list[tuple[Any, ...]]:
    return [
        candle_row(
            minute_offset=count - index,
            volume=volume,
        )
        for index in range(count)
    ]


def build_plugin(
    rows: list[tuple[Any, ...]],
    *,
    settings: VolumeFlowSettings | None = None,
) -> tuple[VolumeFlowPlugin, FakeStore]:
    store = FakeStore(rows)
    plugin = VolumeFlowPlugin(
        store=store,
        settings=settings or VolumeFlowSettings(),
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


def test_short_history_computes_rvol_but_not_zscore() -> None:
    rows = volume_rows(count=10, volume=1000)
    plugin, _ = build_plugin(rows)

    result = plugin.build(build_context())
    timeframe = result["timeframes"]["1m"]

    assert result["complete"] is True
    assert timeframe["rvol"] == 1.0
    assert timeframe["volume_zscore"] is None
    assert timeframe["available_bars"] == 9


def test_sufficient_history_computes_volume_metrics() -> None:
    rows = volume_rows(count=31, volume=1000)
    plugin, _ = build_plugin(rows)

    result = plugin.build(build_context())
    timeframe = result["timeframes"]["1m"]

    assert result["available"] is True
    assert result["complete"] is True
    assert timeframe["latest_volume"] == 1000
    assert timeframe["average_volume"] == 1000
    assert timeframe["rvol"] == 1.0
    assert timeframe["volume_zscore"] is None
    assert timeframe["volume_trend"] == "FLAT"
    assert timeframe["available_bars"] == 30


def test_high_volume_has_rising_trend() -> None:
    rows = volume_rows(count=31, volume=1000)
    rows[29] = candle_row(
        minute_offset=2,
        volume=2000,
    )

    plugin, _ = build_plugin(rows)

    result = plugin.build(build_context())
    timeframe = result["timeframes"]["1m"]

    assert timeframe["latest_volume"] == 2000
    assert timeframe["average_volume"] == 1000
    assert timeframe["rvol"] == 2.0
    assert timeframe["volume_trend"] == "RISING"


def test_future_candles_are_excluded() -> None:
    rows = volume_rows(count=31, volume=1000)
    rows.append(
        (
            DECISION_TS + timedelta(minutes=1),
            100.0,
            101.0,
            99.0,
            100.0,
            5000,
        )
    )

    plugin, store = build_plugin(rows)
    result = plugin.build(build_context())

    assert result["bars_used"] == 31

    _query, params = store.conn.queries[0]
    assert params[1] == DECISION_TS


def test_plugin_error_is_contained_by_runner() -> None:
    class FailingConnection:
        def execute(self, *_args: Any, **_kwargs: Any) -> Any:
            raise RuntimeError("database unavailable")

    class FailingStore:
        conn = FailingConnection()

    plugin = VolumeFlowPlugin(
        store=FailingStore(),
        settings=VolumeFlowSettings(enabled=True),
    )

    results = EvidencePluginRunner([plugin]).run(build_context())

    assert len(results) == 1
    assert results[0].plugin == "volume_flow"
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
        volume_rows(count=31, volume=1000),
        settings=VolumeFlowSettings(
            timeframes=[timeframe],
        ),
    )

    with pytest.raises(ValueError, match="Unsupported timeframe"):
        plugin.build(build_context())
