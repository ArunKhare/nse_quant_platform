"""Tests for the event-impact outcome reaction recorder."""

from __future__ import annotations

from datetime import UTC, datetime

import duckdb

from nse_quant.research.event_reaction_recorder import (
    EventReaction,
    classify_reaction,
    initialize_event_reactions,
    read_event_reactions,
    record_event_reaction,
)


def _reaction(**changes):
    values = dict(
        impact_id="imp1",
        run_id="run1",
        ts=datetime(2026, 1, 1, 10, 5, tzinfo=UTC),
        event_id="evt1",
        event_type="RBI_POLICY",
        instrument="NIFTY",
        spot_return_5m_pct=-1.5,
        spot_return_15m_pct=-2.0,
        spot_return_30m_pct=-2.5,
        spot_return_60m_pct=-3.0,
        realized_range=120.0,
        atm_iv_change=-0.05,
        expected_move_change=-20.0,
        pcr_change=0.1,
        oi_change=1000.0,
        option_spread_change=0.5,
        strategy_pnl_impact=-500.0,
    )
    values.update(changes)
    return EventReaction(**values)


def test_record_and_read_roundtrip(tmp_path):
    with duckdb.connect(str(tmp_path / "test.duckdb")) as conn:
        initialize_event_reactions(conn)
        reaction = _reaction()
        result = record_event_reaction(conn, reaction)
        assert result["status"] == "RECORDED"
        assert result["decision_eligibility_asserted"] is False
        rows = read_event_reactions(conn, event_id="evt1")
        assert len(rows) == 1
        assert rows[0]["impact_id"] == "imp1"
        assert rows[0]["instrument"] == "NIFTY"
        assert rows[0]["spot_return_5m_pct"] == -1.5


def test_record_idempotent(tmp_path):
    with duckdb.connect(str(tmp_path / "test.duckdb")) as conn:
        initialize_event_reactions(conn)
        reaction = _reaction()
        first = record_event_reaction(conn, reaction)
        second = record_event_reaction(conn, reaction)
        assert first["status"] == "RECORDED"
        assert second["status"] == "ALREADY_RECORDED"
        assert second["decision_eligibility_asserted"] is False
        rows = read_event_reactions(conn, event_id="evt1")
        assert len(rows) == 1


def test_read_filter_by_instrument(tmp_path):
    with duckdb.connect(str(tmp_path / "test.duckdb")) as conn:
        initialize_event_reactions(conn)
        record_event_reaction(conn, _reaction())
        record_event_reaction(conn, _reaction(impact_id="imp2", instrument="BANKNIFTY"))
        nifty = read_event_reactions(conn, instrument="NIFTY")
        bank = read_event_reactions(conn, instrument="BANKNIFTY")
        assert len(nifty) == 1 and len(bank) == 1
        assert nifty[0]["instrument"] == "NIFTY"
        assert bank[0]["instrument"] == "BANKNIFTY"


def test_classify_adverse_move():
    reaction = _reaction(spot_return_5m_pct=-1.0, atm_iv_change=None)
    assert classify_reaction(reaction) == "ADVERSE_MOVE"


def test_classify_iv_crush():
    reaction = _reaction(spot_return_5m_pct=0.5, atm_iv_change=-0.03)
    assert classify_reaction(reaction) == "IV_CRUSH"


def test_classify_observed():
    reaction = _reaction(spot_return_5m_pct=0.5, atm_iv_change=0.02)
    assert classify_reaction(reaction) == "OBSERVED"


def test_classify_insufficient_data():
    reaction = _reaction(spot_return_5m_pct=None, atm_iv_change=None)
    assert classify_reaction(reaction) == "INSUFFICIENT_DATA"


def test_to_dict_shape():
    reaction = _reaction()
    doc = reaction.to_dict()
    assert doc["decision_eligibility_asserted"] is False
    assert doc["impact_id"] == "imp1"
    assert doc["event_id"] == "evt1"
    assert "spot_return_5m_pct" in doc
