"""Tests for full integrated and operational acceptance evaluation."""

from __future__ import annotations

from nse_quant.data_platform.operational_acceptance import (
    AcceptanceCriteria,
    evaluate_operational_acceptance,
)


def _criteria(
    package_qa: bool = True,
    integration: bool = True,
    operational: bool = True,
):
    return AcceptanceCriteria(
        package_qa_passed=package_qa,
        integration_tests_passed=integration,
        operational_checks_passed=operational,
    )


def test_all_criteria_pass_accepted():
    result = evaluate_operational_acceptance(criteria=_criteria())
    assert result.accepted is True
    assert result.reasons == []
    assert len(result.checks) == 3
    assert result.production_cutover_authorized is False
    assert result.live_trading_authorized is False


def test_package_qa_not_passed_refused():
    result = evaluate_operational_acceptance(criteria=_criteria(package_qa=False))
    assert result.accepted is False
    assert "PACKAGE_QA_NOT_PASSED" in result.reasons


def test_integration_not_passed_refused():
    result = evaluate_operational_acceptance(criteria=_criteria(integration=False))
    assert result.accepted is False
    assert "INTEGRATION_TESTS_NOT_PASSED" in result.reasons


def test_operational_not_passed_refused():
    result = evaluate_operational_acceptance(criteria=_criteria(operational=False))
    assert result.accepted is False
    assert "OPERATIONAL_CHECKS_NOT_PASSED" in result.reasons


def test_production_cutover_never_authorized():
    result = evaluate_operational_acceptance(criteria=_criteria())
    assert result.production_cutover_authorized is False
    assert result.live_trading_authorized is False


def test_invalid_criteria_refused():
    result = evaluate_operational_acceptance(criteria="not_a_criteria")
    assert result.accepted is False
    assert "INVALID_CRITERIA" in result.reasons
