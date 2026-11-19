"""Tests for refusal loop closure integration."""

from __future__ import annotations

from nse_quant.data_platform.refusal_loop_closure_integration import (
    close_refusal_loop,
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


def _valid_lifecycle_recovery_result():
    return dict(
        reconciled=True,
        reason="LIFECYCLE_RECOVERY_RECONCILED",
        violations=[],
    )


def test_valid_refusal_result_loop_closed():
    result = close_refusal_loop(
        refusal_result=_valid_refusal_result(),
        lifecycle_recovery_result=_valid_lifecycle_recovery_result(),
    )
    assert result["closed"] is True
    assert result["reason"] == "REFUSAL_LOOP_CLOSED"
    assert result["loop_result"] is not None
    assert result["loop_result"]["integrated"] is True


def test_non_dict_refusal_result_refused():
    result = close_refusal_loop(
        refusal_result="not_a_dict",
        lifecycle_recovery_result=_valid_lifecycle_recovery_result(),
    )
    assert result["closed"] is False
    assert result["reason"] == "REFUSAL_RESULT_OBJECT_REQUIRED"
    assert result["loop_result"] is None


def test_non_dict_lifecycle_recovery_result_refused():
    result = close_refusal_loop(
        refusal_result=_valid_refusal_result(),
        lifecycle_recovery_result="not_a_dict",
    )
    assert result["closed"] is False
    assert result["reason"] == "LIFECYCLE_RECOVERY_RESULT_OBJECT_REQUIRED"
    assert result["loop_result"] is None


def test_lifecycle_recovery_not_reconciled_rejected():
    candidate = _valid_lifecycle_recovery_result()
    candidate["reconciled"] = False
    result = close_refusal_loop(
        refusal_result=_valid_refusal_result(),
        lifecycle_recovery_result=candidate,
    )
    assert result["closed"] is False
    assert result["reason"] == "LIFECYCLE_RECOVERY_NOT_RECONCILED"
    assert result["loop_result"] is None


def test_missing_reconciled_flag_defaults_to_false():
    candidate = _valid_lifecycle_recovery_result()
    del candidate["reconciled"]
    result = close_refusal_loop(
        refusal_result=_valid_refusal_result(),
        lifecycle_recovery_result=candidate,
    )
    assert result["closed"] is False
    assert result["reason"] == "LIFECYCLE_RECOVERY_NOT_RECONCILED"
    assert result["loop_result"] is None
