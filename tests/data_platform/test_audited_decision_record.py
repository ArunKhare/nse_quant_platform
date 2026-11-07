"""Tests for actual audited native strategy/risk decision record."""

from __future__ import annotations

from nse_quant.data_platform.audited_decision_record import (
    DecisionRecord,
    audit_decision,
)


def test_strategy_decision_audited():
    record = DecisionRecord(
        stage="strategy",
        inputs=dict(x=1),
        outcome=dict(approved=True),
    )
    result = audit_decision(record=record)
    assert result.recorded is True
    assert result.stage == "strategy"
    assert result.fingerprint != ""
    assert result.reason == "DECISION_AUDITED"
    assert result.decision_eligibility_asserted is False


def test_portfolio_risk_decision_audited():
    record = DecisionRecord(
        stage="portfolio_risk",
        inputs=dict(y=2),
        outcome=dict(approved=False),
    )
    result = audit_decision(record=record)
    assert result.recorded is True
    assert result.stage == "portfolio_risk"
    assert result.fingerprint != ""
    assert result.reason == "DECISION_AUDITED"


def test_unsupported_stage_refused():
    record = DecisionRecord(
        stage="execution",
        inputs=dict(z=3),
        outcome=dict(approved=True),
    )
    result = audit_decision(record=record)
    assert result.recorded is False
    assert result.reason == "UNSUPPORTED_STAGE"


def test_deterministic_fingerprint():
    record = DecisionRecord(
        stage="strategy",
        inputs=dict(x=1),
        outcome=dict(approved=True),
    )
    first = audit_decision(record=record)
    second = audit_decision(record=record)
    assert first.fingerprint == second.fingerprint


def test_different_inputs_different_fingerprint():
    first = audit_decision(
        record=DecisionRecord(stage="strategy", inputs=dict(x=1), outcome=dict(approved=True))
    )
    second = audit_decision(
        record=DecisionRecord(stage="strategy", inputs=dict(x=2), outcome=dict(approved=True))
    )
    assert first.fingerprint != second.fingerprint


def test_invalid_record_refused():
    result = audit_decision(record="not_a_record")
    assert result.recorded is False
    assert result.reason == "INVALID_RECORD"
