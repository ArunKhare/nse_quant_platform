"""Tests for bounded event-risk plugin."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import duckdb
import pytest
from pydantic import ValidationError

from nse_quant.research.event_risk_plugin import (
    EventRiskPlugin,
    EventRiskSettings,
)

AT = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)


def build_store():
    conn = duckdb.connect()
    conn.execute(
        """
        CREATE TABLE market_events (
            event_id VARCHAR PRIMARY KEY,
            source VARCHAR,
            event_type VARCHAR,
            title VARCHAR,
            description TEXT,
            symbol VARCHAR,
            event_ts TIMESTAMPTZ,
            importance VARCHAR,
            consensus_value DOUBLE,
            actual_value DOUBLE,
            surprise_label VARCHAR,
            affected_underlyings JSON,
            raw_payload JSON,
            ingested_at TIMESTAMPTZ
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE event_impact_evidence (
            impact_id VARCHAR PRIMARY KEY,
            run_id VARCHAR,
            ts TIMESTAMPTZ,
            event_id VARCHAR,
            event_type VARCHAR,
            instrument VARCHAR,
            direction VARCHAR,
            volatility_impact VARCHAR,
            liquidity_impact VARCHAR,
            confidence DOUBLE,
            recommended_action VARCHAR,
            payload JSON
        )
        """
    )
    conn.execute(
        "INSERT INTO market_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            "event-1",
            "manual_review",
            "RBI_POLICY",
            "title",
            "description",
            "NIFTY",
            AT,
            "high",
            None,
            None,
            None,
            '["NIFTY"]',
            "{}",
            AT,
        ],
    )
    return SimpleNamespace(conn=conn)


def build_plugin(store, **overrides):
    defaults = {
        "enabled": True,
        "block_new_entries": True,
        "blackout_minutes_before": 30,
        "blackout_minutes_after": 30,
        "allowed_event_types": ["RBI_POLICY"],
        "max_events": 10,
    }
    defaults.update(overrides)
    return EventRiskPlugin(
        store=store,
        settings=EventRiskSettings(**defaults),
    )


def test_blocks_high_impact_event():
    store = build_store()
    plugin = build_plugin(store)
    result = plugin.evaluate(
        run_id="run-1",
        instrument="NIFTY",
        decision_ts=AT,
    )
    assert result["available"] is True
    assert result["event_risk"]["blocked_new_entries"] is True
    assert result["event_risk"]["matched_events"] == 1
    count = store.conn.execute("SELECT count(*) FROM event_impact_evidence").fetchone()[0]
    assert count == 1


def test_disabled_plugin_returns_unavailable():
    plugin = build_plugin(build_store(), enabled=False)
    result = plugin.evaluate(
        run_id="run-1",
        instrument="NIFTY",
        decision_ts=AT,
    )
    assert result["available"] is False
    assert result["reason"] == "event_risk_disabled"


def test_naive_timestamp_rejected():
    plugin = build_plugin(build_store())
    result = plugin.evaluate(
        run_id="run-1",
        instrument="NIFTY",
        decision_ts=datetime(2026, 1, 1, 10, 0),
    )
    assert result["available"] is False
    assert result["reason"] == "aware_decision_timestamp_required"


def test_no_matching_event_returns_no_block():
    store = build_store()
    plugin = build_plugin(store)
    result = plugin.evaluate(
        run_id="run-1",
        instrument="BANKNIFTY",
        decision_ts=AT,
    )
    assert result["available"] is True
    assert result["event_risk"]["blocked_new_entries"] is False
    assert result["event_risk"]["matched_events"] == 0


def test_invalid_settings_rejected():
    with pytest.raises(ValidationError):
        EventRiskSettings(max_events=0)
    with pytest.raises(ValidationError):
        EventRiskSettings(allowed_event_types=[" "])
