"""Tests for refusal-to-acceptance integration."""

from __future__ import annotations

from nse_quant.data_platform.operational_acceptance import AcceptanceCriteria
from nse_quant.data_platform.refusal_acceptance_integration import (
    integrate_refusal_into_acceptance,
)


def _valid_criteria():
    return AcceptanceCriteria(
        package_qa_passed=True,
        integration_tests_passed=True,
        operational_checks_passed=True,
    )


def _valid_refusal_loop_result():
    return dict(
        integrated=True,
        reason="REFUSAL_INTEGRATED_INTO_LOOP",
        audited=None,
        existing_audited=None,
    )


def test_valid_refusal_loop_result_accepted():
    result = integrate_refusal_into_acceptance(
        refusal_loop_result=_valid_refusal_loop_result(),
        criteria=_valid_criteria(),
    )
    assert result.accepted is True
    assert result.reasons == []
    assert result.production_cutover_authorized is False
    assert result.live_trading_authorized is False


def test_refusal_not_integrated_rejected():
    candidate = _valid_refusal_loop_result()
    candidate["integrated"] = False
    result = integrate_refusal_into_acceptance(
        refusal_loop_result=candidate,
        criteria=_valid_criteria(),
    )
    assert result.accepted is False
    assert result.reasons == ["REFUSAL_NOT_INTEGRATED_INTO_LOOP"]


def test_missing_integrated_flag_defaults_to_false():
    candidate = _valid_refusal_loop_result()
    del candidate["integrated"]
    result = integrate_refusal_into_acceptance(
        refusal_loop_result=candidate,
        criteria=_valid_criteria(),
    )
    assert result.accepted is False
    assert result.reasons == ["REFUSAL_NOT_INTEGRATED_INTO_LOOP"]


def test_non_dict_refusal_loop_result_refused():
    result = integrate_refusal_into_acceptance(
        refusal_loop_result="not_a_dict",
        criteria=_valid_criteria(),
    )
    assert result.accepted is False
    assert result.reasons == ["REFUSAL_LOOP_RESULT_OBJECT_REQUIRED"]


def test_non_criteria_refused():
    result = integrate_refusal_into_acceptance(
        refusal_loop_result=_valid_refusal_loop_result(),
        criteria="not_criteria",
    )
    assert result.accepted is False
    assert result.reasons == ["INVALID_CRITERIA"]


def test_failing_criteria_rejected_even_with_integrated_refusal():
    criteria = AcceptanceCriteria(
        package_qa_passed=False,
        integration_tests_passed=True,
        operational_checks_passed=True,
    )
    result = integrate_refusal_into_acceptance(
        refusal_loop_result=_valid_refusal_loop_result(),
        criteria=criteria,
    )
    assert result.accepted is False
    assert "PACKAGE_QA_NOT_PASSED" in result.reasons
