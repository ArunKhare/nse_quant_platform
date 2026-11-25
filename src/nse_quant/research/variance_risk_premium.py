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

VRP_CALCULATION_VERSION = "variance_risk_premium_v3"

# The trailing estimator is retained for diagnostics only. It is not a
# conditional forecast and must never satisfy the IC entry gate.
EXPECTED_RV_METHOD = "trailing_close_close"
EXPECTED_RV_VERSION = "trailing_close_close_daily_v1"
HAR_RV_METHOD = "har_rv_5m_intraday_plus_overnight"
HAR_RV_VERSION = "har_rv_30d_v1"
HAR_RV_HORIZON_DAYS = 30
HAR_RV_MEASURE = "sum_squared_5m_log_returns_plus_squared_overnight_return"
TRADING_DAYS_PER_YEAR = 252


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
    expected_realized_volatility_method: str = EXPECTED_RV_METHOD,
    expected_realized_volatility_version: str = EXPECTED_RV_VERSION,
    expected_realized_volatility_horizon_days: int | None = None,
    expected_realized_volatility_measure: str = "",
    expected_realized_volatility_is_forecast: bool = False,
    implied_volatility_source: str = "unspecified",
    implied_volatility_is_30d_constant_maturity: bool = False,
) -> VarianceRiskPremiumResult:
    """Evaluate VRP using annualized volatility inputs.

    Both inputs must be finite, non-negative annualized volatility values.
    Numeric trailing-RV results remain available for diagnostics, but cannot
    pass the gate. Passing requires an explicitly identified 30-day HAR-RV
    forecast built from 5-minute intraday returns plus the overnight return,
    and VRP strictly above minimum_vrp. Estimator metadata is provenance supplied
    by the caller; this function does not fit or validate a HAR model.
    """
    reasons: list[str] = []
    details: dict[str, Any] = {
        "minimum_vrp": minimum_vrp,
        "formula": "IV^2 - E[RV^2]",
        "threshold_comparison": ">",
        "gate_version": "variance_risk_premium_gate_har_and_iv30_v3",
        "expected_realized_volatility_method": expected_realized_volatility_method,
        "expected_realized_volatility_version": expected_realized_volatility_version,
        "expected_realized_volatility_horizon_days": expected_realized_volatility_horizon_days,
        "expected_realized_volatility_measure": expected_realized_volatility_measure,
        "expected_realized_volatility_is_forecast": expected_realized_volatility_is_forecast,
        "implied_volatility_source": implied_volatility_source,
        "implied_volatility_is_30d_constant_maturity": implied_volatility_is_30d_constant_maturity,
    }
    estimator_eligible = (
        expected_realized_volatility_method == HAR_RV_METHOD
        and expected_realized_volatility_version == HAR_RV_VERSION
        and expected_realized_volatility_horizon_days == HAR_RV_HORIZON_DAYS
        and expected_realized_volatility_measure == HAR_RV_MEASURE
        and expected_realized_volatility_is_forecast is True
    )
    details["estimator_gate_eligible"] = estimator_eligible
    iv_eligible = (
        isinstance(implied_volatility_source, str)
        and bool(implied_volatility_source)
        and implied_volatility_is_30d_constant_maturity is True
    )
    details["implied_volatility_gate_eligible"] = iv_eligible

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

    vrp_positive = variance_risk_premium > minimum_vrp
    passed = estimator_eligible and iv_eligible and vrp_positive
    if not estimator_eligible:
        reasons.append("expected_rv_estimator_not_gate_eligible")
    if not iv_eligible:
        reasons.append("implied_volatility_not_30d_constant_maturity")
    if not vrp_positive:
        reasons.append(
            "variance_risk_premium_at_minimum"
            if variance_risk_premium == minimum_vrp
            else "variance_risk_premium_below_minimum"
        )

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


def trailing_daily_realized_volatility(
    closes: list[float],
    *,
    window_days: int,
) -> tuple[float | None, dict[str, Any]]:
    """Annualized close-to-close realized volatility from completed daily closes.

    Uses the last window_days daily log returns (window_days + 1 closes),
    sample standard deviation, annualized with sqrt(252). Returns (None, ...)
    when there are too few valid closes.
    """
    if window_days < 2:
        raise ValueError("window_days must be at least 2")
    valid = [float(c) for c in closes if c is not None and math.isfinite(float(c)) and float(c) > 0.0]
    details: dict[str, Any] = {
        "method": EXPECTED_RV_METHOD,
        "version": EXPECTED_RV_VERSION,
        "gate_eligible": False,
        "diagnostic_only": True,
        "window_days": window_days,
        "annualization_days": TRADING_DAYS_PER_YEAR,
        "closes_available": len(valid),
        "closes_required": window_days + 1,
    }
    if len(valid) < window_days + 1:
        details["reason"] = "insufficient_daily_closes"
        return None, details
    tail = valid[-(window_days + 1) :]
    returns = [math.log(tail[i] / tail[i - 1]) for i in range(1, len(tail))]
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    rv = math.sqrt(variance) * math.sqrt(TRADING_DAYS_PER_YEAR)
    details["reason"] = None
    return rv, details
