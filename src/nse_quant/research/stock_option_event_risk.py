"""Stock-option event-risk rules; research-only evaluator, no execution authority."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EventRiskRules:
    blackout_days_before: int = 3
    blackout_days_after: int = 1
    size_reduction_factor: float = 0.5
    block_short_volatility: bool = True


def evaluate_event_risk(
    *,
    event_date: str | None,
    as_of_date: str | None,
    days_to_event: int | None,
    days_since_event: int | None,
    settings: EventRiskRules | None = None,
) -> dict[str, Any]:
    """Evaluate stock-option event risk (earnings blackout, size reduction); observational only."""
    settings = settings or EventRiskRules()
    failures: list[str] = []
    actions: list[str] = []

    if event_date is None:
        failures.append("missing_event_date")
    if as_of_date is None:
        failures.append("missing_as_of_date")
    if days_to_event is None:
        failures.append("missing_days_to_event")
    if days_since_event is None:
        failures.append("missing_days_since_event")

    block_new_entry = False
    reduce_size = False
    if days_to_event is not None and days_to_event <= settings.blackout_days_before:
        block_new_entry = True
        actions.append("block_new_entry")
    if days_since_event is not None and days_since_event <= settings.blackout_days_after:
        block_new_entry = True
        actions.append("block_new_entry")
    if days_to_event is not None and 0 < days_to_event <= settings.blackout_days_before * 2:
        reduce_size = True
        actions.append("reduce_size")
    if days_since_event is not None and 0 < days_since_event <= settings.blackout_days_after * 2:
        reduce_size = True
        actions.append("reduce_size")
    if settings.block_short_volatility and block_new_entry:
        actions.append("block_short_volatility")

    return {
        "available": True,
        "block_new_entry": block_new_entry,
        "reduce_size": reduce_size,
        "size_reduction_factor": settings.size_reduction_factor if reduce_size else 1.0,
        "actions": actions,
        "failures": failures,
        "settings": {
            "blackout_days_before": settings.blackout_days_before,
            "blackout_days_after": settings.blackout_days_after,
            "size_reduction_factor": settings.size_reduction_factor,
            "block_short_volatility": settings.block_short_volatility,
        },
        "decision_eligibility_asserted": False,
    }
