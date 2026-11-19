"""Tests for refusal acceptance closure integration."""

from __future__ import annotations

from nse_quant.data_platform.operational_acceptance import AcceptanceCriteria
from nse_quant.data_platform.refusal_acceptance_closure_integration import (
    integrate_closed_loop_into_acceptance,
)


def _valid_criteria():
    return AcceptanceCriteria(
        package_qa_passed=True,
        integration_tests_passed=True,
        operational_checks_passed=True,
    )


def _valid_closed_loop_result():
    return dict(
        closed=True,
        reason="REFUSAL_LOOP_CLOSED",
        loop_result=None,
    )


def test_valid_closed_loop_result_accepted():
    result = integrate_closed_loop_into_acceptance(
        closed_loop_result=_valid_closed_loop_result(),
        criteria=_valid_criteria(),
    )
    assert result.accepted is True
    assert result.reasons == []
    assert result.production_cutover_authorized is False
    assert result.live_trading_authorized is False


def test_loop_not_closed_rejected():
    candidate = _valid_closed_loop_result()
    candidate["closed"] = False
    result = integrate_closed_loop_into_acceptance(
        closed_loop_result=candidate,
        criteria=_valid_criteria(),
    )
    assert result.accepted is False
    assert result.reasons == ["REFUSAL_LOOP_NOT_CLOSED"]


def test_missing_closed_flag_defaults_to_false():
    candidate = _valid_closed_loop_result()
    del candidate["closed"]
    result = integrate_closed_loop_into_acceptance(
        closed_loop_result=candidate,
        criteria=_valid_criteria(),
    )
    assert result.accepted is False
    assert result.reasons == ["REFUSAL_LOOP_NOT_CLOSED"]


def test_non_dict_closed_loop_result_refused():
    result = integrate_closed_loop_into_acceptance(
        closed_loop_result="not_a_dict",
        criteria=_valid_criteria(),
    )
    assert result.accepted is False
    assert result.reasons == ["CLOSED_LOOP_RESULT_OBJECT_REQUIRED"]


def test_non_criteria_refused():
    result = integrate_closed_loop_into_acceptance(
        closed_loop_result=_valid_closed_loop_result(),
        criteria="not_criteria",
    )
    assert result.accepted is False
    assert result.reasons == ["INVALID_CRITERIA"]


def test_failing_criteria_rejected_even_with_closed_loop():
    criteria = AcceptanceCriteria(
        package_qa_passed=False,
        integration_tests_passed=True,
        operational_checks_passed=True,
    )
    result = integrate_closed_loop_into_acceptance(
        closed_loop_result=_valid_closed_loop_result(),
        criteria=criteria,
    )
    assert result.accepted is False
    assert "PACKAGE_QA_NOT_PASSED" in result.reasons
