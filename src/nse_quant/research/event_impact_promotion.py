"""Event impact promotion evaluator.

Consumes event outcome panel results and decides whether an event impact rule
qualifies for promotion to a hard eligibility gate. This is research evidence
only; it does not authorize execution or create a decision gate on its own.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EventImpactPromotionSettings(BaseModel):
    min_events: int = Field(default=30, ge=1)
    min_adverse_move_rate: float = Field(default=0.5, ge=0.0, le=1.0)
    min_iv_crush_rate: float = Field(default=0.2, ge=0.0, le=1.0)
    max_mean_spot_return_pct: float = Field(default=0.0)
    min_regimes: int = Field(default=3, ge=1)


def evaluate_promotion(
    *,
    outcomes: list[dict[str, Any]],
    regimes: list[str],
    settings: EventImpactPromotionSettings | None = None,
) -> dict[str, Any]:
    settings = settings or EventImpactPromotionSettings()

    total = len(outcomes)
    if total < settings.min_events:
        return {
            "status": "NOT_PROMOTED",
            "reason": "insufficient_events",
            "total_outcomes": total,
            "required_events": settings.min_events,
            "decision_eligibility_asserted": False,
        }

    adverse = sum(1 for o in outcomes if o.get("outcome") == "ADVERSE_MOVE")
    iv_crush = sum(1 for o in outcomes if o.get("outcome") == "IV_CRUSH")
    adverse_rate = adverse / total if total else 0.0
    iv_crush_rate = iv_crush / total if total else 0.0

    spot_returns = [o["spot_return_pct"] for o in outcomes if o.get("spot_return_pct") is not None]
    mean_spot_return = sum(spot_returns) / len(spot_returns) if spot_returns else None

    unique_regimes = len(set(regimes))
    if unique_regimes < settings.min_regimes:
        return {
            "status": "NOT_PROMOTED",
            "reason": "insufficient_regimes",
            "total_outcomes": total,
            "unique_regimes": unique_regimes,
            "required_regimes": settings.min_regimes,
            "decision_eligibility_asserted": False,
        }

    if adverse_rate < settings.min_adverse_move_rate:
        return {
            "status": "NOT_PROMOTED",
            "reason": "insufficient_adverse_move_rate",
            "adverse_move_rate": adverse_rate,
            "required_adverse_move_rate": settings.min_adverse_move_rate,
            "decision_eligibility_asserted": False,
        }

    if iv_crush_rate < settings.min_iv_crush_rate:
        return {
            "status": "NOT_PROMOTED",
            "reason": "insufficient_iv_crush_rate",
            "iv_crush_rate": iv_crush_rate,
            "required_iv_crush_rate": settings.min_iv_crush_rate,
            "decision_eligibility_asserted": False,
        }

    if mean_spot_return is not None and mean_spot_return > settings.max_mean_spot_return_pct:
        return {
            "status": "NOT_PROMOTED",
            "reason": "mean_spot_return_above_threshold",
            "mean_spot_return_pct": mean_spot_return,
            "max_mean_spot_return_pct": settings.max_mean_spot_return_pct,
            "decision_eligibility_asserted": False,
        }

    return {
        "status": "PROMOTION_ELIGIBLE",
        "total_outcomes": total,
        "adverse_move_rate": adverse_rate,
        "iv_crush_rate": iv_crush_rate,
        "mean_spot_return_pct": mean_spot_return,
        "unique_regimes": unique_regimes,
        "decision_eligibility_asserted": False,
    }
