"""Tests for look-ahead-safe event-to-instrument impact mapping."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import duckdb
import pytest

from nse_quant.core.settings import EventRiskSettings
from nse_quant.research.evidence_plugins.base import DecisionContext
from nse_quant.research.evidence_plugins.event_impact import EventImpactMapper
from nse_quant.research.evidence_plugins.registry import EvidencePluginRunner

AT = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)


def context() -> DecisionContext:
    return DecisionContext(
        run_id="run-1",
        symbol="NIFTY",
        ts=AT,
        features={},
        snapshot={},
        iv_history_count=30,
        current_regime="RANGE",
        effective_regimes=[],
        regime_policy=None,
        spot_instrument_token=256265,
    )


def settings() -> EventRiskSettings:
    return EventRiskSettings(
        enabled=True,
        block_new_entries=False,
        blackout_minutes_before=30,
        blackout_minutes_after=30,
    )


def seed(conn, *, event_minutes=15, ingested_minutes=-60, affected=None):
    payload = "null" if affected is None else json.dumps(affected)
    ingested_at = None if ingested_minutes is None else AT + timedelta(minutes=ingested_minutes)
    conn.execute(
        "INSERT INTO market_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            "event-1",
            "fixture",
            "RBI_POLICY",
            "RBI policy",
            "description",
            "NIFTY",
            AT + timedelta(minutes=event_minutes),
            "high",
            None,
            None,
            None,
            payload,
            "{}",
            ingested_at,
        ],
    )


def build(rows):
    with duckdb.connect() as conn:
        conn.execute(
            """
            CREATE TABLE market_events (
                event_id VARCHAR, source VARCHAR, event_type VARCHAR, title VARCHAR,
                description TEXT, symbol VARCHAR, event_ts TIMESTAMPTZ,
                importance VARCHAR, consensus_value DOUBLE, actual_value DOUBLE,
                surprise_label VARCHAR, affected_underlyings JSON, raw_payload JSON,
                ingested_at TIMESTAMPTZ
            )
            """
        )
        for row in rows:
            seed(conn, **row)
        mapper = EventImpactMapper(store=SimpleNamespace(conn=conn), settings=settings())
        return mapper.build(context())


def test_dict_mapping_preserves_retained_fields():
    result = build(
        [
            dict(
                affected={
                    "NIFTY": {
                        "direction": "conditional",
                        "volatility_impact": "high",
                        "liquidity_impact": "medium",
                        "confidence": 0.8,
                    }
                }
            )
        ]
    )
    assert result["available"] is True
    assert result["complete"] is True
    assert result["mapped_events"] == 1
    mapping = result["instrument_mappings"][0]
    assert mapping["instrument"] == "NIFTY"
    assert mapping["direction"] == "conditional"
    assert mapping["volatility_impact"] == "high"
    assert mapping["liquidity_impact"] == "medium"
    assert mapping["confidence"] == 0.8
    assert mapping["recommended_action"] == "OBSERVE"
    assert result["block_new_entries"] is False
    assert result["decision_eligibility_asserted"] is False


def test_list_mapping_yields_empty_detail_fields():
    result = build([dict(affected=["NIFTY"])])
    mapping = result["instrument_mappings"][0]
    assert mapping["direction"] is None
    assert mapping["volatility_impact"] is None
    assert mapping["liquidity_impact"] is None
    assert mapping["confidence"] is None


def test_other_symbol_is_not_mapped():
    result = build([dict(affected=["BANKNIFTY"])])
    assert result["mapped_events"] == 0
    assert result["instrument_mappings"] == []


def test_malformed_mapping_is_incomplete_not_fatal():
    result = build([dict(affected="not-json")])
    assert result["available"] is True
    assert result["complete"] is False
    assert result["mapped_events"] == 0


@pytest.mark.parametrize(
    ("event_minutes", "ingested_minutes", "expected"),
    [
        (-31, -60, 0),
        (-30, -60, 1),
        (0, 0, 1),
        (30, -60, 1),
        (31, -60, 0),
        (15, 1, 0),
        (15, None, 0),
    ],
)
def test_blackout_and_ingestion_boundaries(event_minutes, ingested_minutes, expected):
    result = build(
        [dict(event_minutes=event_minutes, ingested_minutes=ingested_minutes, affected=["NIFTY"])]
    )
    assert result["events_considered"] == expected
    assert result["mapped_events"] == expected


def test_plugin_error_is_contained_by_runner():
    class FailingConnection:
        def execute(self, *_args, **_kwargs):
            raise RuntimeError("database unavailable")

    plugin = EventImpactMapper(
        store=SimpleNamespace(conn=FailingConnection()),
        settings=settings(),
    )
    results = EvidencePluginRunner([plugin]).run(context())
    assert len(results) == 1
    assert results[0].plugin == "event_impact"
    assert results[0].available is False
    assert results[0].complete is False
    assert results[0].payload["available"] is False
    assert results[0].payload["error"] == "database unavailable"
    assert results[0].payload["error_type"] == "RuntimeError"
