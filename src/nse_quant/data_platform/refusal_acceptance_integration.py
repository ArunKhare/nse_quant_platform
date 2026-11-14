"""Refusal-to-acceptance integration.

Integrates the refusal loop replay integration's output (refusal_loop_replay_integration.py)
into the acceptance evaluation (operational_acceptance.py), without granting
eligibility or enabling live trading. Addresses the "integrate the refusal loop
replay integration's output into the acceptance evaluation" sub-gap of gate 7
from docs/CURRENT_NATIVE_STATUS.md.
"""

from __future__ import annotations

from typing import Any

from nse_quant.data_platform.operational_acceptance import (
    AcceptanceCriteria,
    AcceptanceDecision,
    evaluate_operational_acceptance,
)


def integrate_refusal_into_acceptance(
    *,
    refusal_loop_result: dict[str, Any],
    criteria: AcceptanceCriteria,
) -> AcceptanceDecision:
    """Integrate the refusal loop replay integration's output into the acceptance evaluation."""
    if type(refusal_loop_result) is not dict:
        return AcceptanceDecision(
            accepted=False,
            reasons=["REFUSAL_LOOP_RESULT_OBJECT_REQUIRED"],
        )
    if type(criteria) is not AcceptanceCriteria:
        return AcceptanceDecision(
            accepted=False,
            reasons=["INVALID_CRITERIA"],
        )

    refusal_integrated = refusal_loop_result.get("integrated", False)
    if type(refusal_integrated) is not bool:
        refusal_integrated = False

    # Require refusal integration as an additional acceptance criterion
    if not refusal_integrated:
        return AcceptanceDecision(
            accepted=False,
            reasons=["REFUSAL_NOT_INTEGRATED_INTO_LOOP"],
        )

    return evaluate_operational_acceptance(criteria=criteria)
