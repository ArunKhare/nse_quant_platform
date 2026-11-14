"""Tests for refusal-to-audited-record integration."""

from __future__ import annotations

from nse_quant.data_platform.refusal_audited_record import (
    build_audited_record_from_refusal,
)


def _valid_refusal_result():
    return dict(
        status="REFUSED_PRE_STRATEGY",
        failed_stage="publication_admission",
        reason_codes=("POINT_IN_TIME_ADMISSION_REJECTED",),
        stage_trace=[
            dict(stage="kill_switch", status="PASSED"),
            dict(stage="safety_boundary", status="PASSED"),
            dict(stage="publication_admission", status="BLOCKED"),
            dict(stage="native_inputs", status="NOT_RUN"),
            dict(stage="strategy", status="NOT_RUN"),
            dict(stage="portfolio_risk", status="NOT_RUN"),
            dict(stage="execution", status="NOT_RUN"),
        ],
        input_requirements_version="iron-condor-proposal-input-requirements@1",
        input_requirements_sha256="a" * 64,
        input_inventory=[],
        inventory_scope="DIRECT_PROPOSAL_REQUIREMENTS_NOT_COMPLETE_PORTFOLIO_OR_LOOP",
        safety_observation_origin="EXPLICIT_REQUEST_NOT_AUTHENTICATED_LIVE_SWITCH_OBSERVATION",
        admission_observed=True,
        strategy_evaluated=False,
        portfolio_risk_evaluated=False,
        execution_attempted=False,
        order_emitted=False,
        decision_eligibility_asserted=False,
        complete_strategy_replay_asserted=False,
    )


def test_valid_refusal_result_produces_audited_record():
    result = build_audited_record_from_refusal(refusal_result=_valid_refusal_result())
    assert result.recorded is True
    assert result.reason == "DECISION_AUDITED"
    assert result.stage == "strategy"
    assert result.fingerprint != ""
    assert result.decision_eligibility_asserted is False


def test_non_dict_refusal_result_refused():
    result = build_audited_record_from_refusal(refusal_result="not_a_dict")
    assert result.recorded is False
    assert result.reason == "REFUSAL_RESULT_OBJECT_REQUIRED"
    assert result.stage == "unknown"
    assert result.fingerprint == ""


def test_missing_failed_stage_defaults_to_strategy():
    candidate = _valid_refusal_result()
    del candidate["failed_stage"]
    result = build_audited_record_from_refusal(refusal_result=candidate)
    assert result.stage == "strategy"
    assert result.recorded is True


def test_portfolio_risk_stage_mapped():
    candidate = _valid_refusal_result()
    candidate["failed_stage"] = "portfolio_risk"
    result = build_audited_record_from_refusal(refusal_result=candidate)
    assert result.stage == "portfolio_risk"
    assert result.recorded is True


def test_unknown_stage_defaults_to_strategy():
    candidate = _valid_refusal_result()
    candidate["failed_stage"] = "unknown_stage"
    result = build_audited_record_from_refusal(refusal_result=candidate)
    assert result.stage == "strategy"
    assert result.recorded is True


def test_fingerprint_deterministic():
    result1 = build_audited_record_from_refusal(refusal_result=_valid_refusal_result())
    result2 = build_audited_record_from_refusal(refusal_result=_valid_refusal_result())
    assert result1.fingerprint == result2.fingerprint


def test_fingerprint_changes_with_input():
    result1 = build_audited_record_from_refusal(refusal_result=_valid_refusal_result())
    candidate = _valid_refusal_result()
    candidate["reason_codes"] = ("DIFFERENT_REASON",)
    result2 = build_audited_record_from_refusal(refusal_result=candidate)
    assert result1.fingerprint != result2.fingerprint
