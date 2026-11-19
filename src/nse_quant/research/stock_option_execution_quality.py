"""Stock-option execution quality; research-only evaluator, no execution authority."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ExecutionQualitySettings:
    max_quote_age_seconds: float = 300.0
    max_spread_pct: float = 2.0
    min_depth: int = 50
    min_risk_reward: float = 1.0
    max_expected_slippage_pct: float = 0.5
    max_time_to_event_days: float = 3.0


def evaluate_execution_quality(
    *,
    quote_age_seconds: float | None,
    bid: float | None,
    ask: float | None,
    depth: int | None,
    risk_reward_ratio: float | None,
    expected_slippage_pct: float | None,
    time_to_event_days: float | None,
    settings: ExecutionQualitySettings | None = None,
) -> dict[str, Any]:
    """Evaluate stock-option execution quality; observational only."""
    settings = settings or ExecutionQualitySettings()
    failures: list[str] = []

    spread_pct: float | None = None
    if quote_age_seconds is None or quote_age_seconds > settings.max_quote_age_seconds:
        failures.append("quote_too_stale_or_missing")
    if bid is not None and ask is not None and bid > 0:
        spread_pct = (ask - bid) / bid * 100.0
        if spread_pct > settings.max_spread_pct:
            failures.append("spread_too_wide")
    else:
        failures.append("missing_or_invalid_quote")
    if depth is None or depth < settings.min_depth:
        failures.append("insufficient_depth")
    if risk_reward_ratio is None or risk_reward_ratio < settings.min_risk_reward:
        failures.append("insufficient_risk_reward")
    if expected_slippage_pct is None or expected_slippage_pct > settings.max_expected_slippage_pct:
        failures.append("slippage_too_high_or_missing")
    if time_to_event_days is None or time_to_event_days <= settings.max_time_to_event_days:
        failures.append("event_risk_too_close_or_missing")

    tradeable = not failures
    return {
        "available": True,
        "tradeable": tradeable,
        "spread_pct": spread_pct,
        "failures": failures,
        "settings": {
            "max_quote_age_seconds": settings.max_quote_age_seconds,
            "max_spread_pct": settings.max_spread_pct,
            "min_depth": settings.min_depth,
            "min_risk_reward": settings.min_risk_reward,
            "max_expected_slippage_pct": settings.max_expected_slippage_pct,
            "max_time_to_event_days": settings.max_time_to_event_days,
        },
        "decision_eligibility_asserted": False,
    }


def classify_execution_quality(result: dict[str, Any]) -> str:
    """Classify execution quality as GOOD, ACCEPTABLE, or POOR from an evaluate_execution_quality result."""
    if not result.get("available"):
        return "POOR"
    failures = result.get("failures", [])
    if not failures:
        return "GOOD"
    if len(failures) <= 2 and all(
        f in {"quote_too_stale_or_missing", "slippage_too_high_or_missing"} for f in failures
    ):
        return "ACCEPTABLE"
    return "POOR"
