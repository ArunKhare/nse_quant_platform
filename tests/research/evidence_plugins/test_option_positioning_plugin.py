"""Tests for look-ahead-safe options-positioning evidence."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import Mock

import pytest

from nse_quant.core.models import (
    ChainSnapshot,
    MarketFeatures,
    OptionQuote,
)
from nse_quant.core.settings import OptionPositioningSettings
from nse_quant.research.evidence_plugins.base import DecisionContext
from nse_quant.research.evidence_plugins.option_positioning import (
    OptionPositioningPlugin,
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

        _, as_of = params[0], params[1]

        filtered_rows = [row for row in self._rows if row[0] < as_of]

        return FakeResult(filtered_rows)


class FakeStore:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self.conn = FakeConnection(rows)


def build_context(
    snapshot: ChainSnapshot | None,
    *,
    atm_iv: float | None = None,
    expected_move_points: float | None = None,
) -> DecisionContext:
    return DecisionContext(
        run_id="run-1",
        symbol="NIFTY",
        ts=DECISION_TS,
        features=MarketFeatures(
            ts=DECISION_TS,
            underlying="NIFTY",
            spot=24_000.0,
            expiry=DECISION_TS.date(),
            atm_iv=atm_iv,
            expected_move_points=expected_move_points,
        ),
        snapshot=snapshot,
        iv_history_count=30,
        current_regime="RANGE",
        effective_regimes=[],
        regime_policy=None,
        spot_instrument_token=256265,
    )


def build_snapshot(
    *,
    call_oi: int,
    put_oi: int,
) -> ChainSnapshot:
    call_instrument = Mock()
    call_instrument.option_type.value = "CE"

    put_instrument = Mock()
    put_instrument.option_type.value = "PE"

    call_quote = Mock(spec=OptionQuote)
    call_quote.instrument = call_instrument
    call_quote.oi = call_oi

    put_quote = Mock(spec=OptionQuote)
    put_quote.instrument = put_instrument
    put_quote.oi = put_oi

    snapshot = Mock(spec=ChainSnapshot)
    snapshot.quotes = [call_quote, put_quote]

    return snapshot


def prior_payload(
    *,
    call_oi: int,
    put_oi: int,
    atm_iv: float,
    expected_move: float,
) -> str:
    return json.dumps(
        {
            "quotes": [
                {
                    "instrument": {
                        "option_type": "CE",
                    },
                    "oi": call_oi,
                },
                {
                    "instrument": {
                        "option_type": "PE",
                    },
                    "oi": put_oi,
                },
            ],
            "atm_iv": atm_iv,
            "expected_move": expected_move,
        }
    )


def build_plugin(
    rows: list[tuple[Any, ...]],
    *,
    settings: OptionPositioningSettings | None = None,
) -> tuple[OptionPositioningPlugin, FakeStore]:
    store = FakeStore(rows)
    plugin = OptionPositioningPlugin(
        store=store,
        settings=settings or OptionPositioningSettings(),
    )
    return plugin, store


def test_no_prior_snapshot_is_incomplete() -> None:
    snapshot = build_snapshot(
        call_oi=100_000,
        put_oi=120_000,
    )

    plugin, _ = build_plugin([])

    result = plugin.build(build_context(snapshot))

    assert result["available"] is True
    assert result["complete"] is False
    assert result["pcr"] == 1.2
    assert result["pcr_change"] is None
    assert result["atm_iv_change"] is None
    assert result["expected_move_change"] is None
    assert result["reason"] == "no_prior_snapshot"


def test_prior_snapshot_computes_changes() -> None:
    snapshot = build_snapshot(
        call_oi=100_000,
        put_oi=120_000,
    )

    prior = prior_payload(
        call_oi=100_000,
        put_oi=110_000,
        atm_iv=0.15,
        expected_move=190.0,
    )

    plugin, _ = build_plugin(
        [
            (
                DECISION_TS - timedelta(minutes=1),
                prior,
            )
        ]
    )

    result = plugin.build(
        build_context(
            snapshot,
            atm_iv=0.14,
            expected_move_points=180.0,
        )
    )

    assert result["available"] is True
    assert result["complete"] is True
    assert result["pcr"] == pytest.approx(1.2)
    assert result["pcr_change"] == pytest.approx(0.1)
    assert result["call_oi_change"] == 0
    assert result["put_oi_change"] == 10_000
    assert result["atm_iv_change"] == pytest.approx(-0.01)
    assert result["expected_move_change"] == pytest.approx(-10.0)


def test_iv_crush_is_detected() -> None:
    snapshot = build_snapshot(
        call_oi=100_000,
        put_oi=120_000,
    )

    prior = prior_payload(
        call_oi=100_000,
        put_oi=110_000,
        atm_iv=0.15,
        expected_move=190.0,
    )

    plugin, _ = build_plugin(
        [
            (
                DECISION_TS - timedelta(minutes=1),
                prior,
            )
        ],
        settings=OptionPositioningSettings(
            iv_crush_decline_pct=20.0,
        ),
    )

    result = plugin.build(
        build_context(
            snapshot,
            atm_iv=0.10,
            expected_move_points=180.0,
        )
    )

    assert result["iv_crush_risk"] is True


def test_put_skewed_positioning_is_detected() -> None:
    snapshot = build_snapshot(
        call_oi=100_000,
        put_oi=130_000,
    )

    plugin, _ = build_plugin([])

    result = plugin.build(build_context(snapshot))

    assert result["positioning_bias"] == "PUT_SKEWED"


def test_future_snapshot_is_not_used() -> None:
    snapshot = build_snapshot(
        call_oi=100_000,
        put_oi=120_000,
    )

    future_payload = prior_payload(
        call_oi=100_000,
        put_oi=110_000,
        atm_iv=0.20,
        expected_move=250.0,
    )

    plugin, store = build_plugin(
        [
            (
                DECISION_TS + timedelta(minutes=1),
                future_payload,
            )
        ]
    )

    result = plugin.build(build_context(snapshot))

    assert result["complete"] is False
    assert result["atm_iv_change"] is None

    _query, params = store.conn.queries[0]
    assert params[1] == DECISION_TS


def test_plugin_error_is_contained_by_runner() -> None:
    class FailingConnection:
        def execute(self, *_args: Any, **_kwargs: Any) -> Any:
            raise RuntimeError("database unavailable")

    class FailingStore:
        conn = FailingConnection()

    plugin = OptionPositioningPlugin(
        store=FailingStore(),
        settings=OptionPositioningSettings(enabled=True),
    )

    results = EvidencePluginRunner([plugin]).run(
        build_context(
            build_snapshot(
                call_oi=100_000,
                put_oi=120_000,
            )
        )
    )

    assert len(results) == 1
    assert results[0].plugin == "option_positioning"
    assert results[0].available is False
    assert results[0].complete is False
    assert results[0].payload["available"] is False
    assert results[0].payload["error_type"] == "RuntimeError"
