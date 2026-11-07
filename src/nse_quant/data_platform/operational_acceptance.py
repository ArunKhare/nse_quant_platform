"""Full integrated and operational acceptance evaluation.

Evaluates a set of acceptance criteria (package QA passed, integration tests
passed, operational checks passed) and returns an acceptance decision, without
granting production cutover or live trading. Addresses gate 7 from
docs/CURRENT_NATIVE_STATUS.md.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AcceptanceCriteria(BaseModel):
    package_qa_passed: bool
    integration_tests_passed: bool
    operational_checks_passed: bool


class AcceptanceDecision(BaseModel):
    accepted: bool
    reasons: list[str] = Field(default_factory=list)
    checks: list[dict[str, Any]] = Field(default_factory=list)
    production_cutover_authorized: bool = False
    live_trading_authorized: bool = False


def evaluate_operational_acceptance(
    *,
    criteria: AcceptanceCriteria,
) -> AcceptanceDecision:
    """Evaluate full integrated and operational acceptance criteria."""
    if type(criteria) is not AcceptanceCriteria:
        return AcceptanceDecision(accepted=False, reasons=["INVALID_CRITERIA"])

    checks: list[dict[str, Any]] = []
    reasons: list[str] = []

    checks.append(dict(check="package_qa_passed", passed=criteria.package_qa_passed))
    if not criteria.package_qa_passed:
        reasons.append("PACKAGE_QA_NOT_PASSED")

    checks.append(dict(check="integration_tests_passed", passed=criteria.integration_tests_passed))
    if not criteria.integration_tests_passed:
        reasons.append("INTEGRATION_TESTS_NOT_PASSED")

    checks.append(
        dict(check="operational_checks_passed", passed=criteria.operational_checks_passed)
    )
    if not criteria.operational_checks_passed:
        reasons.append("OPERATIONAL_CHECKS_NOT_PASSED")

    return AcceptanceDecision(
        accepted=not reasons,
        reasons=reasons,
        checks=checks,
        production_cutover_authorized=False,
        live_trading_authorized=False,
    )
