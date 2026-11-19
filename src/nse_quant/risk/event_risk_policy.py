"""Event-aware risk policy.

Produces a conservative, explainable risk recommendation from event-impact
evidence and an optional observed reaction. This is advisory only: it never
places, modifies, or cancels orders and never bypasses the kill switch.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EventRiskPolicySettings(BaseModel):
    enabled: bool = False
    reduce_size_on_high_volatility: bool = False
    max_size_reduction_pct: float = Field(default=50.0, ge=0.0, le=100.0)
    review_iv_crush_threshold: float = Field(default=-0.02, le=0.0)

    @property
    def size_multiplier(self) -> float:
        return 1.0 - self.max_size_reduction_pct / 100.0


class EventRiskDecision(BaseModel):
    action: str
    size_multiplier: float
    reasons: list[str] = Field(default_factory=list)
    decision_eligibility_asserted: bool = False


def evaluate_event_risk(
    *,
    event_impact: dict[str, Any] | None,
    reaction: dict[str, Any] | None,
    settings: EventRiskPolicySettings,
) -> EventRiskDecision:
    if not settings.enabled:
        return EventRiskDecision(
            action="OBSERVE",
            size_multiplier=1.0,
            reasons=["event_risk_policy_disabled"],
        )

    impact = event_impact or {}
    observed = reaction or {}

    if impact.get("block_new_entries") is True:
        return EventRiskDecision(
            action="BLOCK_NEW_ENTRIES",
            size_multiplier=0.0,
            reasons=["high_impact_event_within_blackout_window"],
        )

    volatility_impact = impact.get("volatility_impact")
    if settings.reduce_size_on_high_volatility and volatility_impact == "high":
        return EventRiskDecision(
            action="REDUCE_SIZE",
            size_multiplier=settings.size_multiplier,
            reasons=["high_volatility_event_impact"],
        )

    iv_change = observed.get("atm_iv_change")
    if iv_change is not None and iv_change <= settings.review_iv_crush_threshold:
        return EventRiskDecision(
            action="REVIEW_OPEN_POSITIONS",
            size_multiplier=1.0,
            reasons=["iv_crush_after_event"],
        )

    return EventRiskDecision(
        action="OBSERVE",
        size_multiplier=1.0,
        reasons=["no_event_risk_rule_triggered"],
    )
