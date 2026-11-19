"""Research lifecycle recovery reconciliation.

Validates that a research lifecycle recovery doesn't heal original failed,
incomplete, unlinked, or orphan obligations by later success, without granting
eligibility or enabling live trading. Addresses the "research lifecycle/recovery
beyond bounded first-write profiles" sub-gap of gate 5 from
docs/CURRENT_NATIVE_STATUS.md.
"""

from __future__ import annotations

from typing import Any

OBLIGATION_STATES = ("failed", "incomplete", "unlinked", "orphan")


def reconcile_lifecycle_recovery(
    *,
    original_obligations: dict[str, str],
    recovery_outcomes: dict[str, str],
) -> dict[str, Any]:
    """Validate that recovery doesn't heal original \
        failed/incomplete/unlinked/orphan obligations."""
    if type(original_obligations) is not dict:
        return dict(
            reconciled=False,
            reason="ORIGINAL_OBLIGATIONS_DICT_REQUIRED",
            violations=["ORIGINAL_OBLIGATIONS_DICT_REQUIRED"],
        )
    if type(recovery_outcomes) is not dict:
        return dict(
            reconciled=False,
            reason="RECOVERY_OUTCOMES_DICT_REQUIRED",
            violations=["RECOVERY_OUTCOMES_DICT_REQUIRED"],
        )

    violations: list[str] = []

    # Check original obligations have valid states
    for obligation_id, state in original_obligations.items():
        if state not in OBLIGATION_STATES:
            violations.append(f"INVALID_ORIGINAL_STATE:{obligation_id}:{state}")

    # Check recovery doesn't heal original failed/incomplete/unlinked/orphan obligations
    for obligation_id, original_state in original_obligations.items():
        recovery_state = recovery_outcomes.get(obligation_id)
        if recovery_state is None:
            continue
        if original_state in OBLIGATION_STATES and recovery_state == "resolved":
            violations.append(f"ORIGINAL_OBLIGATION_HEALED:{obligation_id}")

    reconciled = not violations
    return dict(
        reconciled=reconciled,
        reason="LIFECYCLE_RECOVERY_RECONCILED" if reconciled else "LIFECYCLE_RECOVERY_VIOLATIONS",
        violations=violations,
    )
