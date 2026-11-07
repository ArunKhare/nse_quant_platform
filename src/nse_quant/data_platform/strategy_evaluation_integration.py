"""Strategy evaluation integration.

Combines the outputs of the existing gates (MarketOpenGate, IvRegimeGate,
ExpectedMoveGate, LiquidityGate) plus analytics validation plus portfolio risk
into a single audited strategy decision, without granting eligibility or
enabling live trading. Addresses the "strategy evaluation integration" sub-gap
of gate 6 from docs/CURRENT_NATIVE_STATUS.md.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class GateOutputs(BaseModel):
    market_session_passed: bool
    iv_regime_passed: bool
    expected_move_passed: bool
    liquidity_passed: bool


class AnalyticsOutcome(BaseModel):
    valid: bool


class PortfolioRiskOutcome(BaseModel):
    approved: bool


class IntegratedDecision(BaseModel):
    approved: bool
    reasons: list[str] = Field(default_factory=list)
    checks: list[dict[str, Any]] = Field(default_factory=list)
    decision_eligibility_asserted: bool = False


def integrate_strategy_evaluation(
    *,
    gates: GateOutputs,
    analytics: AnalyticsOutcome,
    portfolio_risk: PortfolioRiskOutcome,
) -> IntegratedDecision:
    """Combine gate, analytics, and portfolio-risk outcomes into one decision."""
    if (
        type(gates) is not GateOutputs
        or type(analytics) is not AnalyticsOutcome
        or type(portfolio_risk) is not PortfolioRiskOutcome
    ):
        return IntegratedDecision(approved=False, reasons=["INVALID_INPUTS"])

    checks: list[dict[str, Any]] = []
    reasons: list[str] = []

    checks.append(dict(check="market_session", passed=gates.market_session_passed))
    if not gates.market_session_passed:
        reasons.append("MARKET_SESSION_FAILED")

    checks.append(dict(check="iv_regime", passed=gates.iv_regime_passed))
    if not gates.iv_regime_passed:
        reasons.append("IV_REGIME_FAILED")

    checks.append(dict(check="expected_move", passed=gates.expected_move_passed))
    if not gates.expected_move_passed:
        reasons.append("EXPECTED_MOVE_FAILED")

    checks.append(dict(check="liquidity", passed=gates.liquidity_passed))
    if not gates.liquidity_passed:
        reasons.append("LIQUIDITY_FAILED")

    checks.append(dict(check="analytics_valid", passed=analytics.valid))
    if not analytics.valid:
        reasons.append("ANALYTICS_INVALID")

    checks.append(dict(check="portfolio_risk_approved", passed=portfolio_risk.approved))
    if not portfolio_risk.approved:
        reasons.append("PORTFOLIO_RISK_NOT_APPROVED")

    return IntegratedDecision(
        approved=not reasons,
        reasons=reasons,
        checks=checks,
        decision_eligibility_asserted=False,
    )
