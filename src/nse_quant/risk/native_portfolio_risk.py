"""Native portfolio-risk evaluation.

Evaluates a trade proposal against portfolio-level limits (max open positions,
max notional exposure, max concentration per underlying). Produces an auditable
risk decision; never places, modifies, or cancels orders and never bypasses the
kill switch.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PortfolioRiskSettings(BaseModel):
    max_open_positions: int = Field(default=5, ge=1)
    max_notional_exposure: float = Field(default=1000000.0, gt=0.0)
    max_concentration_pct: float = Field(default=30.0, gt=0.0, le=100.0)


class PortfolioRiskDecision(BaseModel):
    approved: bool
    reasons: list[str] = Field(default_factory=list)
    checks: list[dict[str, Any]] = Field(default_factory=list)
    decision_eligibility_asserted: bool = False


def evaluate_portfolio_risk(
    *,
    proposal: dict[str, Any],
    open_positions: list[dict[str, Any]],
    settings: PortfolioRiskSettings,
) -> PortfolioRiskDecision:
    if type(proposal) is not dict or "underlying" not in proposal or "notional" not in proposal:
        return PortfolioRiskDecision(
            approved=False,
            reasons=["invalid_proposal"],
        )

    underlying = proposal["underlying"]
    notional = proposal["notional"]

    if type(underlying) is not str or not underlying:
        return PortfolioRiskDecision(approved=False, reasons=["invalid_underlying"])
    if type(notional) not in (int, float) or notional < 0:
        return PortfolioRiskDecision(approved=False, reasons=["invalid_notional"])

    checks: list[dict[str, Any]] = []
    reasons: list[str] = []

    open_count = len(open_positions)
    count_ok = open_count < settings.max_open_positions
    checks.append(
        dict(
            check="max_open_positions",
            passed=count_ok,
            open_count=open_count,
            limit=settings.max_open_positions,
        )
    )
    if not count_ok:
        reasons.append("max_open_positions_exceeded")

    total_notional = (
        sum(pos.get("notional", 0.0) for pos in open_positions if isinstance(pos, dict)) + notional
    )
    notional_ok = total_notional <= settings.max_notional_exposure
    checks.append(
        dict(
            check="max_notional_exposure",
            passed=notional_ok,
            total_notional=total_notional,
            limit=settings.max_notional_exposure,
        )
    )
    if not notional_ok:
        reasons.append("max_notional_exposure_exceeded")

    same_underlying = [
        pos
        for pos in open_positions
        if isinstance(pos, dict) and pos.get("underlying") == underlying
    ]
    same_notional = sum(pos.get("notional", 0.0) for pos in same_underlying) + notional
    concentration = same_notional / settings.max_notional_exposure * 100.0
    concentration_ok = concentration <= settings.max_concentration_pct
    checks.append(
        dict(
            check="max_concentration_pct",
            passed=concentration_ok,
            concentration_pct=concentration,
            limit=settings.max_concentration_pct,
        )
    )
    if not concentration_ok:
        reasons.append("max_concentration_pct_exceeded")

    return PortfolioRiskDecision(
        approved=not reasons,
        reasons=reasons,
        checks=checks,
    )
