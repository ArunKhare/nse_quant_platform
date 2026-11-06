"""Tests for the event-outcome research panel."""

from __future__ import annotations

import duckdb
import pytest

from nse_quant.research.event_outcomes import (
    EventOutcomePanelSettings,
    build_event_outcomes,
    classify_outcome,
    summarize,
)


def build_store():
    conn = duckdb.connect()
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
            surprise_label VARCHAR,
            recommended_action VARCHAR,
            payload JSON
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE event_reactions (
            reaction_id VARCHAR PRIMARY KEY,
            event_id VARCHAR,
            instrument VARCHAR,
            event_ts TIMESTAMPTZ,
            observation_window_minutes INTEGER,
            observed_at TIMESTAMPTZ,
            spot_return_pct DOUBLE,
            realized_range_points DOUBLE,
            atm_iv_change DOUBLE,
            expected_move_change_points DOUBLE,
            pcr_change DOUBLE,
            relevant_oi_change BIGINT,
            option_spread_change_pct DOUBLE,
            payload JSON,
            ingested_at TIMESTAMPTZ
        )
        """
    )
    return conn


def insert_outcome(
    conn,
    *,
    event_id="event-1",
    instrument="NIFTY",
    spot_return=-2.0,
    iv_change=-0.03,
    action="BLOCK_NEW_ENTRIES",
) -> None:
    conn.execute(
        "INSERT INTO event_impact_evidence VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            f"impact-{event_id}-{instrument}",
            "run-1",
            None,
            event_id,
            "RBI_POLICY",
            instrument,
            "conditional",
            "high",
            "medium",
            0.85,
            None,
            action,
            "{}",
        ],
    )
    conn.execute(
        "INSERT INTO event_reactions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            f"reaction-{event_id}-{instrument}",
            event_id,
            instrument,
            None,
            15,
            None,
            spot_return,
            3.0,
            iv_change,
            20.0,
            0.2,
            200,
            0.01,
            "{}",
            None,
        ],
    )


def test_join_matches_event_and_instrument():
    conn = build_store()
    insert_outcome(conn)
    outcomes = build_event_outcomes(conn)
    assert len(outcomes) == 1
    assert outcomes[0]["event_id"] == "event-1"
    assert outcomes[0]["instrument"] == "NIFTY"
    assert outcomes[0]["outcome"] == "ADVERSE_MOVE"


def test_adverse_move_classification():
    settings = EventOutcomePanelSettings(adverse_return_threshold_pct=-1.0)
    assert classify_outcome({"spot_return_pct": -2.0}, settings) == "ADVERSE_MOVE"


def test_iv_crush_classification():
    settings = EventOutcomePanelSettings(iv_crush_threshold=-0.02)
    assert (
        classify_outcome({"spot_return_pct": 0.5, "atm_iv_change": -0.03}, settings) == "IV_CRUSH"
    )


def test_insufficient_data_classification():
    settings = EventOutcomePanelSettings()
    assert classify_outcome({"spot_return_pct": None}, settings) == "INSUFFICIENT_DATA"


def test_empty_store_returns_empty_panel():
    conn = build_store()
    assert build_event_outcomes(conn) == []
    summary = summarize([])
    assert summary["total_outcomes"] == 0
    assert summary["mean_spot_return_pct"] is None


def test_summary_counts_outcomes_and_actions():
    conn = build_store()
    insert_outcome(conn, event_id="event-1", spot_return=-2.0, action="BLOCK_NEW_ENTRIES")
    insert_outcome(conn, event_id="event-2", spot_return=1.0, iv_change=0.01, action="OBSERVE")
    outcomes = build_event_outcomes(conn)
    summary = summarize(outcomes)
    assert summary["total_outcomes"] == 2
    assert summary["by_outcome"]["ADVERSE_MOVE"] == 1
    assert summary["by_outcome"]["OBSERVED"] == 1
    assert summary["by_recommended_action"]["BLOCK_NEW_ENTRIES"] == 1
    assert summary["by_recommended_action"]["OBSERVE"] == 1
    assert summary["mean_spot_return_pct"] == pytest.approx(-0.5)
