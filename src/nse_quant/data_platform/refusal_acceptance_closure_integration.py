"""Refusal acceptance closure integration.

Integrates the closed loop's output (refusal_loop_closure_integration.py) back
into the operational acceptance evaluation (operational_acceptance.py) to
complete the full integrated and operational acceptance, without granting
eligibility or enabling live trading. Addresses the "integrate the closed loop's
output back into the operational acceptance evaluation to complete the full
integrated and operational acceptance" sub-gap of gate 7 from
docs/CURRENT_NATIVE_STATUS.md.
"""

from __future__ import annotations

from typing import Any

from nse_quant.data_platform.operational_acceptance import (
    AcceptanceCriteria,
    AcceptanceDecision,
    evaluate_operational_acceptance,
)


def integrate_closed_loop_into_acceptance(
    *,
    closed_loop_result: dict[str, Any],
    criteria: AcceptanceCriteria,
) -> AcceptanceDecision:
    """Integrate the closed loop's output back into the operational acceptance
    evaluation to complete the full integrated and operational acceptance."""
    if type(closed_loop_result) is not dict:
        return AcceptanceDecision(
            accepted=False,
            reasons=["CLOSED_LOOP_RESULT_OBJECT_REQUIRED"],
        )
    if type(criteria) is not AcceptanceCriteria:
        return AcceptanceDecision(
            accepted=False,
            reasons=["INVALID_CRITERIA"],
        )

    loop_closed = closed_loop_result.get("closed", False)
    if type(loop_closed) is not bool:
        loop_closed = False

    if not loop_closed:
        return AcceptanceDecision(
            accepted=False,
            reasons=["REFUSAL_LOOP_NOT_CLOSED"],
        )

    return evaluate_operational_acceptance(criteria=criteria)
