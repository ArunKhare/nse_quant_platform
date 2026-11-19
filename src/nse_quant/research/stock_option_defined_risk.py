"""Stock-option defined-risk strategies; research-only evaluator, no execution authority."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DefinedRiskSettings:
    max_wing_width: float = 500.0
    min_wing_width: float = 1.0
    require_liquid_wings: bool = True


def evaluate_bull_call_spread(
    *,
    long_strike: float,
    short_strike: float,
    long_premium: float,
    short_premium: float,
    settings: DefinedRiskSettings | None = None,
) -> dict[str, Any]:
    """Evaluate a bull call spread structure; observational only."""
    settings = settings or DefinedRiskSettings()
    failures: list[str] = []
    if long_strike >= short_strike:
        failures.append("long_strike_must_be_below_short_strike")
    wing_width = short_strike - long_strike
    if wing_width < settings.min_wing_width or wing_width > settings.max_wing_width:
        failures.append("wing_width_out_of_range")
    net_debit = long_premium - short_premium
    if net_debit <= 0:
        failures.append("net_debit_must_be_positive")
    max_profit = wing_width - net_debit
    max_loss = net_debit
    return {
        "available": True,
        "valid": not failures,
        "strategy": "bull_call_spread",
        "wing_width": wing_width,
        "net_debit": net_debit,
        "max_profit": max_profit,
        "max_loss": max_loss,
        "risk_reward_ratio": max_profit / max_loss if max_loss > 0 else None,
        "failures": failures,
        "decision_eligibility_asserted": False,
    }


def evaluate_bear_put_spread(
    *,
    long_strike: float,
    short_strike: float,
    long_premium: float,
    short_premium: float,
    settings: DefinedRiskSettings | None = None,
) -> dict[str, Any]:
    """Evaluate a bear put spread structure; observational only."""
    settings = settings or DefinedRiskSettings()
    failures: list[str] = []
    if long_strike <= short_strike:
        failures.append("long_strike_must_be_above_short_strike")
    wing_width = long_strike - short_strike
    if wing_width < settings.min_wing_width or wing_width > settings.max_wing_width:
        failures.append("wing_width_out_of_range")
    net_debit = long_premium - short_premium
    if net_debit <= 0:
        failures.append("net_debit_must_be_positive")
    max_profit = wing_width - net_debit
    max_loss = net_debit
    return {
        "available": True,
        "valid": not failures,
        "strategy": "bear_put_spread",
        "wing_width": wing_width,
        "net_debit": net_debit,
        "max_profit": max_profit,
        "max_loss": max_loss,
        "risk_reward_ratio": max_profit / max_loss if max_loss > 0 else None,
        "failures": failures,
        "decision_eligibility_asserted": False,
    }


def evaluate_iron_condor(
    *,
    put_long_strike: float,
    put_short_strike: float,
    call_short_strike: float,
    call_long_strike: float,
    net_credit: float,
    settings: DefinedRiskSettings | None = None,
) -> dict[str, Any]:
    """Evaluate an iron condor structure; observational only."""
    settings = settings or DefinedRiskSettings()
    failures: list[str] = []
    if put_long_strike >= put_short_strike:
        failures.append("put_long_strike_must_be_below_put_short_strike")
    if call_short_strike >= call_long_strike:
        failures.append("call_short_strike_must_be_below_call_long_strike")
    if net_credit <= 0:
        failures.append("net_credit_must_be_positive")
    put_wing = put_short_strike - put_long_strike
    call_wing = call_long_strike - call_short_strike
    if put_wing < settings.min_wing_width or put_wing > settings.max_wing_width:
        failures.append("put_wing_width_out_of_range")
    if call_wing < settings.min_wing_width or call_wing > settings.max_wing_width:
        failures.append("call_wing_width_out_of_range")
    max_loss = max(put_wing, call_wing) - net_credit
    return {
        "available": True,
        "valid": not failures,
        "strategy": "iron_condor",
        "put_wing_width": put_wing,
        "call_wing_width": call_wing,
        "net_credit": net_credit,
        "max_loss": max_loss,
        "failures": failures,
        "decision_eligibility_asserted": False,
    }


def evaluate_iron_fly(
    *,
    put_long_strike: float,
    center_strike: float,
    call_long_strike: float,
    net_credit: float,
    settings: DefinedRiskSettings | None = None,
) -> dict[str, Any]:
    """Evaluate an iron fly structure; observational only."""
    settings = settings or DefinedRiskSettings()
    failures: list[str] = []
    if put_long_strike >= center_strike:
        failures.append("put_long_strike_must_be_below_center_strike")
    if call_long_strike <= center_strike:
        failures.append("call_long_strike_must_be_above_center_strike")
    if net_credit <= 0:
        failures.append("net_credit_must_be_positive")
    put_wing = center_strike - put_long_strike
    call_wing = call_long_strike - center_strike
    if put_wing < settings.min_wing_width or put_wing > settings.max_wing_width:
        failures.append("put_wing_width_out_of_range")
    if call_wing < settings.min_wing_width or call_wing > settings.max_wing_width:
        failures.append("call_wing_width_out_of_range")
    max_loss = max(put_wing, call_wing) - net_credit
    return {
        "available": True,
        "valid": not failures,
        "strategy": "iron_fly",
        "put_wing_width": put_wing,
        "call_wing_width": call_wing,
        "net_credit": net_credit,
        "max_loss": max_loss,
        "failures": failures,
        "decision_eligibility_asserted": False,
    }
