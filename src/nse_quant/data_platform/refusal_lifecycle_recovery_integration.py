"""Refusal-to-lifecycle-recovery integration.

Integrates the refusal admission integration's output (refusal_admission_integration.py)
into the research lifecycle recovery evaluation (research_lifecycle_recovery.py),
without granting eligibility or enabling live trading. Addresses the "integrate
the refusal admission integration's output into the research lifecycle recovery
evaluation" sub-gap of gate 5 from docs/CURRENT_NATIVE_STATUS.md.
"""

from __future__ import annotations

from typing import Any

from nse_quant.data_platform.research_lifecycle_recovery import (
    reconcile_lifecycle_recovery,
)


def integrate_refusal_into_lifecycle_recovery(
    *,
    refusal_admission_result: dict[str, Any],
    original_obligations: dict[str, str],
    recovery_outcomes: dict[str, str],
) -> dict[str, Any]:
    """Integrate the refusal admission integration's output into the research
    lifecycle recovery evaluation."""
    if type(refusal_admission_result) is not dict:
        return dict(
            integrated=False,
            reason="REFUSAL_ADMISSION_RESULT_OBJECT_REQUIRED",
            reconciled=False,
        )
    if type(original_obligations) is not dict:
        return dict(
            integrated=False,
            reason="ORIGINAL_OBLIGATIONS_DICT_REQUIRED",
            reconciled=False,
        )
    if type(recovery_outcomes) is not dict:
        return dict(
            integrated=False,
            reason="RECOVERY_OUTCOMES_DICT_REQUIRED",
            reconciled=False,
        )

    refusal_integrated = refusal_admission_result.get("integrated", False)
    if type(refusal_integrated) is not bool:
        refusal_integrated = False

    if not refusal_integrated:
        return dict(
            integrated=False,
            reason="REFUSAL_NOT_INTEGRATED_INTO_ADMISSION",
            reconciled=False,
        )

    recovery = reconcile_lifecycle_recovery(
        original_obligations=original_obligations,
        recovery_outcomes=recovery_outcomes,
    )
    integrated = recovery.get("reconciled", False)
    return dict(
        integrated=integrated,
        reason="REFUSAL_INTEGRATED_INTO_LIFECYCLE_RECOVERY"
        if integrated
        else "LIFECYCLE_RECOVERY_NOT_RECONCILED",
        reconciled=integrated,
    )
