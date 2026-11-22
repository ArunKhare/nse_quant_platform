"""Variance risk premium validation for iron-condor entries.

VRP = IV^2 - E[RV^2]

A positive VRP is required before an iron-condor entry may be considered.
This module is research/validation evidence only. It does not grant decision
eligibility, execution authority, or live-trading authority.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

VRP_CALCULATION_VERSION = "variance_risk_premium_v1"


@dataclass(frozen=True)
class VarianceRiskPremiumResult:
    calculation_version: str
    available: bool
    passed: bool
    implied_volatility: float | None
    expected_realized_variance: float | None
    variance_risk_premium: float | None
    reasons: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


def evaluate_variance_risk_premium(
    *,
    implied_volatility: float | None,
    expected_realized_volatility: float | None,
    minimum_vrp: float = 0.0,
) -> VarianceRiskPremiumResult:
    """Evaluate VRP using annualized volatility inputs.

    Both inputs must be finite, non-negative annualized volatility values. The
    result is unavailable, not failed, when either input is missing or invalid.
    """
    reasons: list[str] = []
    details: dict[str, Any] = {
        "minimum_vrp": minimum_vrp,
        "formula": "IV^2 - E[RV^2]",
    }

    iv, iv_reason = _validate_volatility(implied_volatility, "implied_volatility")
    rv, rv_reason = _validate_volatility(
        expected_realized_volatility,
        "expected_realized_volatility",
    )
    if iv_reason is not None:
        reasons.append(iv_reason)
    if rv_reason is not None:
        reasons.append(rv_reason)

    if iv is None or rv is None:
        return VarianceRiskPremiumResult(
            calculation_version=VRP_CALCULATION_VERSION,
            available=False,
            passed=False,
            implied_volatility=iv,
            expected_realized_variance=None,
            variance_risk_premium=None,
            reasons=reasons,
            details=details,
        )

    # iv and rv are plain floats from here on.
    implied_variance = iv**2
    expected_realized_variance = rv**2
    variance_risk_premium = implied_variance - expected_realized_variance

    details.update(
        {
            "implied_variance": implied_variance,
            "expected_realized_variance": expected_realized_variance,
        }
    )

    passed = variance_risk_premium >= minimum_vrp
    if not passed:
        reasons.append("variance_risk_premium_below_minimum")

    return VarianceRiskPremiumResult(
        calculation_version=VRP_CALCULATION_VERSION,
        available=True,
        passed=passed,
        implied_volatility=iv,
        expected_realized_variance=expected_realized_variance,
        variance_risk_premium=variance_risk_premium,
        reasons=reasons,
        details=details,
    )


def _validate_volatility(
    value: float | None,
    name: str,
) -> tuple[float | None, str | None]:
    """Return (volatility, None) when valid, or (None, reason) when not.

    Valid means a finite, non-negative real number. Booleans, NaN, infinity,
    and negative values are invalid; None is unavailable.
    """
    if value is None:
        return None, f"{name}_unavailable"
    if isinstance(value, bool):
        return None, f"{name}_invalid"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None, f"{name}_invalid"
    if not math.isfinite(number) or number < 0.0:
        return None, f"{name}_invalid"
    return number, None
