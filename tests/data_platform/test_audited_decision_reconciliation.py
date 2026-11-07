"""Tests for audited decision reconciliation."""

from __future__ import annotations

from nse_quant.data_platform.audited_decision_reconciliation import (
    EXPECTED_STAGES,
    NOT_RUN_STAGES,
    reconcile_audited_decision,
)


def _valid_decision_result():
    trace = []
    for index, stage in enumerate(EXPECTED_STAGES):
        if stage in NOT_RUN_STAGES:
            trace.append(dict(stage=stage, status="NOT_RUN"))
        else:
            trace.append(dict(stage=stage, status="PASSED" if index < 3 else "BLOCKED"))
    return dict(
        stage_trace=trace,
        strategy_evaluated=False,
        portfolio_risk_evaluated=False,
        execution_attempted=False,
        order_emitted=False,
        decision_eligibility_asserted=False,
        complete_strategy_replay_asserted=False,
    )


def test_valid_decision_reconciled():
    result = reconcile_audited_decision(decision_result=_valid_decision_result())
    assert result["reconciled"] is True
    assert result["reason"] == "AUDITED_DECISION_RECONCILED"
    assert result["violations"] == []


def test_not_run_stage_marked_passed():
    candidate = _valid_decision_result()
    for item in candidate["stage_trace"]:
        if item["stage"] == "strategy":
            item["status"] = "PASSED"
    result = reconcile_audited_decision(decision_result=candidate)
    assert result["reconciled"] is False
    assert result["reason"] == "AUDITED_DECISION_VIOLATIONS"
    assert "NOT_RUN_STAGE_MARKED_PASSED:strategy" in result["violations"]


def test_non_not_run_stage_marked_not_run():
    candidate = _valid_decision_result()
    for item in candidate["stage_trace"]:
        if item["stage"] == "kill_switch":
            item["status"] = "NOT_RUN"
    result = reconcile_audited_decision(decision_result=candidate)
    assert result["reconciled"] is False
    assert result["reason"] == "AUDITED_DECISION_VIOLATIONS"
    assert "NON_NOT_RUN_STAGE_MARKED_NOT_RUN:kill_switch" in result["violations"]


def test_flag_not_false():
    candidate = _valid_decision_result()
    candidate["strategy_evaluated"] = True
    result = reconcile_audited_decision(decision_result=candidate)
    assert result["reconciled"] is False
    assert result["reason"] == "AUDITED_DECISION_VIOLATIONS"
    assert "FLAG_NOT_FALSE:strategy_evaluated" in result["violations"]


def test_decision_eligibility_asserted_not_false():
    candidate = _valid_decision_result()
    candidate["decision_eligibility_asserted"] = True
    result = reconcile_audited_decision(decision_result=candidate)
    assert result["reconciled"] is False
    assert result["reason"] == "AUDITED_DECISION_VIOLATIONS"
    assert "DECISION_ELIGIBILITY_ASSERTED_NOT_FALSE" in result["violations"]


def test_stage_trace_not_list():
    candidate = _valid_decision_result()
    candidate["stage_trace"] = "not_a_list"
    result = reconcile_audited_decision(decision_result=candidate)
    assert result["reconciled"] is False
    assert result["reason"] == "AUDITED_DECISION_VIOLATIONS"
    assert "STAGE_TRACE_NOT_LIST" in result["violations"]


def test_non_dict_refused():
    result = reconcile_audited_decision(decision_result="not_a_dict")
    assert result["reconciled"] is False
    assert result["reason"] == "DECISION_RESULT_OBJECT_REQUIRED"
    assert "DECISION_RESULT_OBJECT_REQUIRED" in result["violations"]
