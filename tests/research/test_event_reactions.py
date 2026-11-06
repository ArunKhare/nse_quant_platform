"""Tests for bounded event-reaction observation capture."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import duckdb
import pytest

from nse_quant.research.event_reactions import (
    EventReactionRecorder,
    EventReactionSettings,
    build_event_reaction,
)

AT = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)


def baseline() -> dict[str, object]:
    return {
        "spot": 100.0,
        "atm_iv": 0.10,
        "expected_move_points": 100.0,
        "pcr": 1.0,
        "relevant_oi": 1000,
        "option_spread_pct": 0.01,
    }


def observed() -> dict[str, object]:
    return {
        "spot": 101.0,
        "high": 102.0,
        "low": 99.0,
        "atm_iv": 0.12,
        "expected_move_points": 120.0,
        "pcr": 1.2,
        "relevant_oi": 1200,
        "option_spread_pct": 0.02,
    }


def build_store() -> SimpleNamespace:
    conn = duckdb.connect()
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
    return SimpleNamespace(conn=conn)


def test_reaction_calculations_are_bounded_and_correct():
    reaction = build_event_reaction(
        baseline=baseline(),
        observed=observed(),
        window_minutes=15,
    )
    assert reaction["available"] is True
    assert reaction["complete"] is True
    assert reaction["spot_return_pct"] == pytest.approx(1.0)
    assert reaction["realized_range_points"] == pytest.approx(3.0)
    assert reaction["atm_iv_change"] == pytest.approx(0.02)
    assert reaction["expected_move_change_points"] == pytest.approx(20.0)
    assert reaction["pcr_change"] == pytest.approx(0.2)
    assert reaction["relevant_oi_change"] == pytest.approx(200)
    assert reaction["option_spread_change_pct"] == pytest.approx(0.01)


def test_missing_observed_fields_are_incomplete_not_fatal():
    reaction = build_event_reaction(
        baseline=baseline(),
        observed={"spot": 101.0},
        window_minutes=15,
    )
    assert reaction["available"] is True
    assert reaction["complete"] is False
    assert reaction["realized_range_points"] is None
    assert reaction["atm_iv_change"] is None


def test_zero_baseline_spot_does_not_divide():
    reaction = build_event_reaction(
        baseline={"spot": 0.0},
        observed={"spot": 101.0},
        window_minutes=15,
    )
    assert reaction["available"] is False
    assert reaction["spot_return_pct"] is None


def test_recorder_persists_configured_window():
    store = build_store()
    recorder = EventReactionRecorder(
        store=store,
        settings=EventReactionSettings(
            enabled=True,
            observation_windows=[15],
        ),
    )
    result = recorder.record(
        event_id="event-1",
        instrument="NIFTY",
        event_ts=AT,
        window_minutes=15,
        baseline=baseline(),
        observed=observed(),
        observed_at=AT + timedelta(minutes=15),
    )
    assert result["reaction_id"]
    row = store.conn.execute(
        "SELECT event_id, instrument, observation_window_minutes FROM event_reactions"
    ).fetchone()
    assert row == ("event-1", "NIFTY", 15)


def test_unconfigured_window_is_rejected():
    recorder = EventReactionRecorder(
        store=build_store(),
        settings=EventReactionSettings(observation_windows=[15]),
    )
    with pytest.raises(ValueError):
        recorder.record(
            event_id="event-1",
            instrument="NIFTY",
            event_ts=AT,
            window_minutes=30,
            baseline=baseline(),
            observed=observed(),
            observed_at=AT + timedelta(minutes=30),
        )


def test_duplicate_reaction_is_idempotent():
    store = build_store()
    recorder = EventReactionRecorder(
        store=store,
        settings=EventReactionSettings(observation_windows=[15]),
    )
    first = recorder.record(
        event_id="event-1",
        instrument="NIFTY",
        event_ts=AT,
        window_minutes=15,
        baseline=baseline(),
        observed=observed(),
        observed_at=AT + timedelta(minutes=15),
    )
    second = recorder.record(
        event_id="event-1",
        instrument="NIFTY",
        event_ts=AT,
        window_minutes=15,
        baseline=baseline(),
        observed=observed(),
        observed_at=AT + timedelta(minutes=15),
    )
    assert first["reaction_id"] == second["reaction_id"]
    count = store.conn.execute("SELECT count(*) FROM event_reactions").fetchone()[0]
    assert count == 1
