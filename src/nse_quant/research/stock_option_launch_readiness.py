"""Stock-option paper strategy launch readiness; research-only evaluator, no execution authority."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LaunchReadinessSettings:
    require_liquidity: bool = True
    require_event_risk_clear: bool = True
    require_defined_risk_valid: bool = True
    require_execution_quality_good: bool = True


def evaluate_launch_readiness(
    *,
    liquidity_result: dict[str, Any] | None,
    event_risk_result: dict[str, Any] | None,
    defined_risk_result: dict[str, Any] | None,
    execution_quality_result: dict[str, Any] | None,
    settings: LaunchReadinessSettings | None = None,
) -> dict[str, Any]:
    """Evaluate stock-option paper-strategy launch readiness; observational only."""
    settings = settings or LaunchReadinessSettings()
    failures: list[str] = []
    checks: dict[str, bool] = {}

    if settings.require_liquidity:
        if liquidity_result is None or not liquidity_result.get("tradable"):
            failures.append("liquidity_not_tradable")
            checks["liquidity"] = False
        else:
            checks["liquidity"] = True
    if settings.require_event_risk_clear:
        if event_risk_result is None or event_risk_result.get("block_new_entry"):
            failures.append("event_risk_blocks_entry")
            checks["event_risk"] = False
        else:
            checks["event_risk"] = True
    if settings.require_defined_risk_valid:
        if defined_risk_result is None or not defined_risk_result.get("valid"):
            failures.append("defined_risk_structure_invalid")
            checks["defined_risk"] = False
        else:
            checks["defined_risk"] = True
    if settings.require_execution_quality_good:
        if execution_quality_result is None or not execution_quality_result.get("tradeable"):
            failures.append("execution_quality_not_tradeable")
            checks["execution_quality"] = False
        else:
            checks["execution_quality"] = True

    ready = not failures
    return {
        "available": True,
        "ready": ready,
        "checks": checks,
        "failures": failures,
        "settings": {
            "require_liquidity": settings.require_liquidity,
            "require_event_risk_clear": settings.require_event_risk_clear,
            "require_defined_risk_valid": settings.require_defined_risk_valid,
            "require_execution_quality_good": settings.require_execution_quality_good,
        },
        "decision_eligibility_asserted": False,
    }


def classify_launch_readiness(result: dict[str, Any]) -> str:
    """Classify launch readiness as READY, CONDITIONAL, or NOT_READY from an evaluate_launch_readiness result."""
    if not result.get("available"):
        return "NOT_READY"
    failures = result.get("failures", [])
    if not failures:
        return "READY"
    if len(failures) == 1 and failures[0] == "execution_quality_not_tradeable":
        return "CONDITIONAL"
    return "NOT_READY"
