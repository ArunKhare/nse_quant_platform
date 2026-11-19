"""Tests for multi-complete-trading-day reliability evidence."""

from __future__ import annotations

from datetime import date

from nse_quant.research.reliability_evidence import (
    ReliabilitySettings,
    TradingDayRecord,
    evaluate_reliability,
    summarize_reliability,
)


def _record(day: int, **changes):
    values = dict(
        trading_day=date(2026, 1, day),
        cycles_run=10,
        cycles_passed=10,
        evidence_complete=True,
        kill_switch_triggered=False,
        errors=0,
    )
    values.update(changes)
    return TradingDayRecord(**values)


def test_insufficient_days():
    records = [_record(1), _record(2)]
    result = evaluate_reliability(records=records, settings=ReliabilitySettings(min_days=3))
    assert result["status"] == "INSUFFICIENT_DAYS"
    assert result["decision_eligibility_asserted"] is False


def test_all_days_pass():
    records = [_record(1), _record(2), _record(3)]
    result = evaluate_reliability(records=records)
    assert result["status"] == "RELIABILITY_EVIDENCE_COMPLETE"
    assert result["total_days"] == 3
    assert result["total_cycles"] == 30
    assert result["total_passed_cycles"] == 30
    assert result["pass_rate"] == 1.0
    assert result["failures"] == []
    assert result["decision_eligibility_asserted"] is False


def test_insufficient_cycles_flags_failure():
    records = [_record(1, cycles_run=0), _record(2), _record(3)]
    result = evaluate_reliability(records=records)
    assert result["status"] == "RELIABILITY_GAPS_FOUND"
    assert any("insufficient_cycles" in f for f in result["failures"])
    assert result["decision_eligibility_asserted"] is False


def test_cycles_not_all_passed_flags_failure():
    records = [_record(1, cycles_passed=8), _record(2), _record(3)]
    result = evaluate_reliability(records=records)
    assert result["status"] == "RELIABILITY_GAPS_FOUND"
    assert any("cycles_not_all_passed" in f for f in result["failures"])
    assert result["decision_eligibility_asserted"] is False


def test_errors_exceeded_flags_failure():
    records = [_record(1, errors=2), _record(2), _record(3)]
    result = evaluate_reliability(records=records)
    assert result["status"] == "RELIABILITY_GAPS_FOUND"
    assert any("errors_exceeded" in f for f in result["failures"])
    assert result["decision_eligibility_asserted"] is False


def test_evidence_incomplete_flags_failure():
    records = [_record(1, evidence_complete=False), _record(2), _record(3)]
    result = evaluate_reliability(records=records)
    assert result["status"] == "RELIABILITY_GAPS_FOUND"
    assert any("evidence_incomplete" in f for f in result["failures"])
    assert result["decision_eligibility_asserted"] is False


def test_kill_switch_triggered_flags_failure():
    records = [_record(1, kill_switch_triggered=True), _record(2), _record(3)]
    result = evaluate_reliability(records=records)
    assert result["status"] == "RELIABILITY_GAPS_FOUND"
    assert any("kill_switch_triggered" in f for f in result["failures"])
    assert result["decision_eligibility_asserted"] is False


def test_kill_switch_allowed_when_configured():
    records = [_record(1, kill_switch_triggered=True), _record(2), _record(3)]
    result = evaluate_reliability(
        records=records, settings=ReliabilitySettings(allow_kill_switch=True)
    )
    assert result["status"] == "RELIABILITY_EVIDENCE_COMPLETE"
    assert result["days_with_kill_switch"] == 1
    assert result["decision_eligibility_asserted"] is False


def test_summarize_reliability_shape():
    records = [_record(1), _record(2), _record(3)]
    summary = summarize_reliability(records)
    assert summary["total_days"] == 3
    assert summary["total_cycles"] == 30
    assert summary["total_passed_cycles"] == 30
    assert summary["pass_rate"] == 1.0
    assert summary["decision_eligibility_asserted"] is False
