"""Stateful event-review alerts for open positions.

Emits at most one alert per transition into a review state. This is advisory
only: it never places, modifies, or cancels orders and never bypasses the kill
switch.
"""

from __future__ import annotations

from typing import Any

from nse_quant.persistence.repositories import DecisionRepository
from nse_quant.risk.event_risk_policy import EventRiskDecision


class EventReviewAlertManager:
    def __init__(self, decisions: DecisionRepository) -> None:
        self.decisions = decisions
        self._last_action: str | None = None

    def evaluate(
        self,
        *,
        run_id: str,
        decision: EventRiskDecision | None,
        open_positions: list[Any],
        notify: Any | None,
    ) -> dict[str, Any] | None:
        if decision is None:
            return None

        action = decision.action
        previous = self._last_action
        self._last_action = action

        if action != "REVIEW_OPEN_POSITIONS":
            return None

        if previous == "REVIEW_OPEN_POSITIONS":
            return None

        if not open_positions:
            return None

        payload = {
            "reason": decision.reasons,
            "open_position_count": len(open_positions),
            "decision": decision.model_dump(mode="json"),
        }
        self.decisions.save_system_event(
            run_id=run_id,
            event_type="event_review_alert",
            payload=payload,
        )

        if notify is not None:
            notify(
                "NSE Quant paper loop: event_review_alert\n"
                f"Open positions: {len(open_positions)}\n"
                f"Reasons: {', '.join(decision.reasons)}"
            )

        return payload
