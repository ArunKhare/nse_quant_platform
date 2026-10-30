"""Tests for look-ahead-safe event-risk evidence."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from nse_quant.core.settings import EventRiskSettings
from nse_quant.research.evidence_plugins.base import DecisionContext
from nse_quant.research.evidence_plugins.event_risk import EventRiskPlugin

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

    def execute(self, query: str, params: list[Any]) -> Any:
        self.queries.append((query, params))

        lower_bound, upper_bound = params[0], params[1]

        filtered_rows = [row for row in self._rows if lower_bound <= row[2] <= upper_bound]

        return FakeResult(filtered_rows)


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


def event_row(
    *,
    event_id: str = "event-1",
    event_type: str = "RBI_POLICY",
    event_ts: datetime = DECISION_TS + timedelta(minutes=15),
    importance: str = "high",
    affected: list[str] | dict[str, Any] | tuple[str, ...] | None = ("NIFTY",),
) -> tuple[Any, ...]:
    return (
        event_id,
        event_type,
        event_ts,
        importance,
        json.dumps(affected),
    )


def build_plugin(
    rows: list[tuple[Any, ...]],
    *,
    settings: EventRiskSettings | None = None,
) -> tuple[EventRiskPlugin, FakeStore]:
    store = FakeStore(rows)
    plugin = EventRiskPlugin(
        store=store,
        settings=settings or EventRiskSettings(),
    )
    return plugin, store


def test_no_events_is_available_and_does_not_block() -> None:
    plugin, _ = build_plugin([])

    result = plugin.build(build_context())

    assert result["available"] is True
    assert result["complete"] is True
    assert result["events_considered"] == 0
    assert result["relevant_events"] == []
    assert result["blocking_events"] == 0
    assert result["recommended_action"] == "OBSERVE"
    assert result["block_new_entries"] is False


def test_relevant_future_event_is_observed_when_blocking_disabled() -> None:
    rows = [event_row()]
    settings = EventRiskSettings(
        enabled=True,
        block_new_entries=False,
    )
    plugin, _ = build_plugin(rows, settings=settings)

    result = plugin.build(build_context())

    assert result["available"] is True
    assert result["complete"] is True
    assert result["events_considered"] == 1
    assert result["blocking_events"] == 1
    assert result["recommended_action"] == "OBSERVE"
    assert result["block_new_entries"] is False


def test_relevant_future_event_blocks_when_enabled() -> None:
    rows = [event_row()]
    settings = EventRiskSettings(
        enabled=True,
        block_new_entries=True,
    )
    plugin, _ = build_plugin(rows, settings=settings)

    result = plugin.build(build_context())

    assert result["blocking_events"] == 1
    assert result["recommended_action"] == "BLOCK_NEW_ENTRIES"
    assert result["block_new_entries"] is True


def test_event_outside_blackout_window_does_not_block() -> None:
    rows = [
        event_row(
            event_ts=DECISION_TS + timedelta(minutes=45),
        )
    ]
    settings = EventRiskSettings(
        enabled=True,
        block_new_entries=True,
        blackout_minutes_before=30,
    )
    plugin, _ = build_plugin(rows, settings=settings)

    result = plugin.build(build_context())

    assert result["events_considered"] == 0
    assert result["blocking_events"] == 0
    assert result["block_new_entries"] is False


def test_event_for_other_underlying_does_not_block() -> None:
    rows = [
        event_row(
            affected=["BANKNIFTY"],
        )
    ]
    settings = EventRiskSettings(
        enabled=True,
        block_new_entries=True,
    )
    plugin, _ = build_plugin(rows, settings=settings)

    result = plugin.build(build_context())

    assert result["events_considered"] == 0
    assert result["blocking_events"] == 0
    assert result["block_new_entries"] is False


def test_non_high_impact_event_does_not_block() -> None:
    rows = [
        event_row(
            event_type="SCHEDULED_EXPIRY",
        )
    ]
    settings = EventRiskSettings(
        enabled=True,
        block_new_entries=True,
    )
    plugin, _ = build_plugin(rows, settings=settings)

    result = plugin.build(build_context())

    assert result["events_considered"] == 1
    assert result["blocking_events"] == 0
    assert result["block_new_entries"] is False


def test_query_is_look_ahead_safe() -> None:
    rows: list[tuple[Any, ...]] = []
    plugin, store = build_plugin(rows)

    plugin.build(build_context())

    assert store.conn.queries, "Expected plugin to query the event store"

    _query, params = store.conn.queries[0]
    lower_bound, upper_bound = params[0], params[1]

    assert lower_bound == DECISION_TS
    assert upper_bound == DECISION_TS + timedelta(minutes=30)


def test_affected_underlyings_accepts_dictionary_mapping() -> None:
    rows = [
        event_row(
            affected={
                "NIFTY": {
                    "direction": "conditional",
                    "volatility_impact": "high",
                }
            },
        )
    ]
    settings = EventRiskSettings(
        enabled=True,
        block_new_entries=True,
    )
    plugin, _ = build_plugin(rows, settings=settings)

    result = plugin.build(build_context())

    assert result["blocking_events"] == 1
    assert result["block_new_entries"] is True


def test_plugin_error_is_contained_by_runner() -> None:
    from nse_quant.research.evidence_plugins.registry import (
        EvidencePluginRunner,
    )

    class FailingConnection:
        def execute(self, *_args: Any, **_kwargs: Any) -> Any:
            raise RuntimeError("database unavailable")

    class FailingStore:
        conn = FailingConnection()

    plugin = EventRiskPlugin(
        store=FailingStore(),
        settings=EventRiskSettings(enabled=True),
    )

    results = EvidencePluginRunner([plugin]).run(build_context())

    assert len(results) == 1
    assert results[0].plugin == "event_risk"
    assert results[0].available is False
    assert results[0].complete is False
    assert results[0].payload["available"] is False
    assert results[0].payload["error"] == "database unavailable"
    assert results[0].payload["error_type"] == "RuntimeError"


@pytest.mark.parametrize(
    "affected",
    [
        None,
        [],
        ["BANKNIFTY"],
    ],
)
def test_unrelated_or_missing_affected_symbols_do_not_block(
    affected: list[str] | None,
) -> None:
    rows = [
        event_row(
            affected=affected,
        )
    ]
    settings = EventRiskSettings(
        enabled=True,
        block_new_entries=True,
    )
    plugin, _ = build_plugin(rows, settings=settings)

    result = plugin.build(build_context())

    assert result["block_new_entries"] is False
