"""Stateful alerts for strategy eligibility transitions."""

from __future__ import annotations

from typing import Any

from nse_quant.persistence.repositories import DecisionRepository


class EligibilityAlertManager:
    def __init__(self, decisions: DecisionRepository) -> None:
        self.decisions = decisions
        self._last_state: bool | None = None
        self._last_reason: str | None = None

    def evaluate(
        self,
        *,
        run_id: str,
        eligibility: dict[str, Any] | None,
        notify: Any | None,
    ) -> dict[str, Any] | None:
        if eligibility is None:
            return None

        passed = bool(eligibility.get("passed"))
        reason = eligibility.get("reason")

        if self._last_state is None:
            self._last_state = passed
            self._last_reason = reason

            if not passed:
                return self._notify(
                    run_id=run_id,
                    event_type="strategy_eligibility_blocked",
                    reason=reason,
                    eligibility=eligibility,
                    notify=notify,
                )

            return None

        if self._last_state == passed:
            return None

        self._last_state = passed
        self._last_reason = reason

        if passed:
            return self._notify(
                run_id=run_id,
                event_type="strategy_eligibility_recovered",
                reason=reason,
                eligibility=eligibility,
                notify=notify,
            )

        return self._notify(
            run_id=run_id,
            event_type="strategy_eligibility_blocked",
            reason=reason,
            eligibility=eligibility,
            notify=notify,
        )

    def _notify(
        self,
        *,
        run_id: str,
        event_type: str,
        reason: str | None,
        eligibility: dict[str, Any],
        notify: Any | None,
    ) -> dict[str, Any] | None:
        payload = {
            "reason": reason,
            "eligibility": eligibility,
        }

        self.decisions.save_system_event(
            run_id=run_id,
            event_type=event_type,
            payload=payload,
        )

        if notify is None:
            return payload

        message = (
            f"NSE Quant paper loop: {event_type}\n"
            f"Reason: {reason}\n"
            f"Regime: "
            f"{eligibility.get('details', {}).get('current_regime')}\n"
            f"IV rank: "
            f"{eligibility.get('details', {}).get('iv_rank')}"
        )

        notify(message)
        return payload