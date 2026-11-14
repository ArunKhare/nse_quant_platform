"""Refusal loop closure integration.

Integrates the research lifecycle recovery evaluation's output (research_lifecycle_recovery.py)
back into the refusal loop replay integration (refusal_loop_replay_integration.py)
to close the loop, without granting eligibility or enabling live trading.
Addresses the "integrate the research lifecycle recovery evaluation's output back
into the refusal loop replay integration to close the loop" sub-gap of gate 6
from docs/CURRENT_NATIVE_STATUS.md.
"""

from __future__ import annotations

from typing import Any

from nse_quant.data_platform.refusal_loop_replay_integration import (
    integrate_refusal_into_loop,
)


def close_refusal_loop(
    *,
    refusal_result: dict[str, Any],
    lifecycle_recovery_result: dict[str, Any],
    existing_audited: Any = None,
) -> dict[str, Any]:
    """Integrate the research lifecycle recovery evaluation's output
    back into the refusal loop replay integration to close the loop."""
    if type(refusal_result) is not dict:
        return dict(
            closed=False,
            reason="REFUSAL_RESULT_OBJECT_REQUIRED",
            loop_result=None,
        )
    if type(lifecycle_recovery_result) is not dict:
        return dict(
            closed=False,
            reason="LIFECYCLE_RECOVERY_RESULT_OBJECT_REQUIRED",
            loop_result=None,
        )

    lifecycle_reconciled = lifecycle_recovery_result.get("reconciled", False)
    if type(lifecycle_reconciled) is not bool:
        lifecycle_reconciled = False

    if not lifecycle_reconciled:
        return dict(
            closed=False,
            reason="LIFECYCLE_RECOVERY_NOT_RECONCILED",
            loop_result=None,
        )

    loop_result = integrate_refusal_into_loop(
        refusal_result=refusal_result,
        existing_audited=existing_audited,
    )
    closed = loop_result.get("integrated", False)
    return dict(
        closed=closed,
        reason="REFUSAL_LOOP_CLOSED" if closed else "REFUSAL_LOOP_NOT_CLOSED",
        loop_result=loop_result,
    )
