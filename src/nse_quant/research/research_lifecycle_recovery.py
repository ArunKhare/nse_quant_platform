"""Research lifecycle/recovery classification.

Classifies research obligations into lifecycle states and explicitly refuses to
heal failed, incomplete, unlinked, or orphan obligations by later success.
This addresses gate 5 from docs/CURRENT_NATIVE_STATUS.md without enabling
live trading or granting decision eligibility.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel


class ObligationState(StrEnum):
    PENDING = "PENDING"
    FAILED = "FAILED"
    INCOMPLETE = "INCOMPLETE"
    UNLINKED = "UNLINKED"
    ORPHAN = "ORPHAN"
    RESOLVED = "RESOLVED"


class LifecycleClassification(BaseModel):
    obligation_id: str
    state: ObligationState
    healable: bool
    reason: str


def classify_obligation(
    *,
    obligation: dict[str, Any],
) -> LifecycleClassification:
    """Classify a single research obligation into a lifecycle state."""
    if type(obligation) is not dict:
        raise ValueError("OBLIGATION_OBJECT_REQUIRED")
    if "obligation_id" not in obligation:
        raise ValueError("OBLIGATION_ID_REQUIRED")

    obligation_id = obligation["obligation_id"]
    if type(obligation_id) is not str or not obligation_id:
        raise ValueError("OBLIGATION_ID_INVALID")

    status = obligation.get("status", "PENDING")
    linked = obligation.get("linked", False)
    has_result = obligation.get("result") is not None

    if status == "FAILED":
        return LifecycleClassification(
            obligation_id=obligation_id,
            state=ObligationState.FAILED,
            healable=False,
            reason="failed_obligations_not_healed_by_later_success",
        )
    if status == "INCOMPLETE":
        return LifecycleClassification(
            obligation_id=obligation_id,
            state=ObligationState.INCOMPLETE,
            healable=False,
            reason="incomplete_obligations_not_healed_by_later_success",
        )
    if not linked and has_result:
        return LifecycleClassification(
            obligation_id=obligation_id,
            state=ObligationState.ORPHAN,
            healable=False,
            reason="orphan_obligations_not_healed_by_later_success",
        )
    if not linked:
        return LifecycleClassification(
            obligation_id=obligation_id,
            state=ObligationState.UNLINKED,
            healable=False,
            reason="unlinked_obligations_not_healed_by_later_success",
        )
    if status == "PENDING" and not has_result:
        return LifecycleClassification(
            obligation_id=obligation_id,
            state=ObligationState.PENDING,
            healable=True,
            reason="pending_obligation_awaiting_result",
        )
    if status == "RESOLVED" and has_result and linked:
        return LifecycleClassification(
            obligation_id=obligation_id,
            state=ObligationState.RESOLVED,
            healable=True,
            reason="resolved_obligation_with_linked_result",
        )
    return LifecycleClassification(
        obligation_id=obligation_id,
        state=ObligationState.INCOMPLETE,
        healable=False,
        reason="unclassifiable_obligation_state",
    )
