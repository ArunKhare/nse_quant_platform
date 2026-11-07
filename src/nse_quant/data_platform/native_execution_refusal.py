"""Native execution-stage refusal record.

Produces an explicit execution-stage refusal record (NOT_RUN) compatible with
the existing refusal decision structure. This completes the stage enumeration
in the refusal record without enabling live trading or granting eligibility.
"""

from __future__ import annotations

from typing import Any

EXECUTION_STAGE = "execution"
NOT_RUN = "NOT_RUN"


def execution_refusal_record(
    *,
    refusal_decision: dict[str, Any],
) -> dict[str, Any]:
    """Explicitly record the execution stage as NOT_RUN in a refusal decision."""
    if type(refusal_decision) is not dict:
        raise ValueError("REFUSAL_DECISION_OBJECT_REQUIRED")
    if "stages" not in refusal_decision:
        raise ValueError("REFUSAL_DECISION_STAGES_REQUIRED")

    stages = refusal_decision["stages"]
    if type(stages) is not dict:
        raise ValueError("REFUSAL_DECISION_STAGES_OBJECT_REQUIRED")

    if EXECUTION_STAGE in stages:
        raise ValueError("EXECUTION_STAGE_ALREADY_RECORDED")

    updated = dict(refusal_decision)
    updated["stages"] = {
        **stages,
        EXECUTION_STAGE: {
            "status": NOT_RUN,
            "reason": "execution_not_authorized",
        },
    }
    return updated
