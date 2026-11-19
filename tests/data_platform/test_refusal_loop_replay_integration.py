"""Tests for refusal-to-full-loop-replay integration."""

from __future__ import annotations

from nse_quant.data_platform.refusal_loop_replay_integration import (
    integrate_refusal_into_loop,
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


def test_valid_refusal_result_integrated():
    result = integrate_refusal_into_loop(refusal_result=_valid_refusal_result())
    assert result["integrated"] is True
    assert result["reason"] == "REFUSAL_INTEGRATED_INTO_LOOP"
    assert result["audited"] is not None
    assert result["audited"].recorded is True
    assert result["existing_audited"] is None


def test_non_dict_refusal_result_refused():
    result = integrate_refusal_into_loop(refusal_result="not_a_dict")
    assert result["integrated"] is False
    assert result["reason"] == "REFUSAL_RESULT_OBJECT_REQUIRED"
    assert result["audited"] is None
    assert result["existing_audited"] is None


def test_with_existing_audited_record():
    from nse_quant.data_platform.audited_decision_record import (
        AuditedDecision,
    )

    existing = AuditedDecision(
        stage="strategy",
        fingerprint="b" * 64,
        recorded=True,
        reason="DECISION_AUDITED",
    )
    result = integrate_refusal_into_loop(
        refusal_result=_valid_refusal_result(),
        existing_audited=existing,
    )
    assert result["integrated"] is True
    assert result["reason"] == "REFUSAL_INTEGRATED_INTO_LOOP"
    assert result["audited"] is not None
    assert result["existing_audited"] is not None
    assert result["existing_audited"].recorded is True


def test_with_unrecorded_existing_audited_record():
    from nse_quant.data_platform.audited_decision_record import (
        AuditedDecision,
    )

    existing = AuditedDecision(
        stage="strategy",
        fingerprint="",
        recorded=False,
        reason="INVALID_RECORD",
    )
    result = integrate_refusal_into_loop(
        refusal_result=_valid_refusal_result(),
        existing_audited=existing,
    )
    assert result["integrated"] is False
    assert result["reason"] == "REFUSAL_NOT_INTEGRATED"
    assert result["audited"] is not None
    assert result["existing_audited"] is not None
    assert result["existing_audited"].recorded is False
