"""Refusal replay reconciliation for stages that actually ran.

Distinguishes between stages that actually ran (kill_switch, safety_boundary,
publication_admission, native_inputs) and stages that didn't run (strategy,
portfolio_risk, execution), matching the refusal-only contract in
native_refusal_decision.py, without granting eligibility or enabling live
trading. Addresses the "complete exact replay of stages that actually run"
sub-gap of gate 6 from docs/CURRENT_NATIVE_STATUS.md.
"""

from __future__ import annotations

from typing import Any

RAN_STAGES = ("kill_switch", "safety_boundary", "publication_admission", "native_inputs")
NOT_RUN_STAGES = ("strategy", "portfolio_risk", "execution")
ALL_STAGES = RAN_STAGES + NOT_RUN_STAGES


def reconcile_refusal_replay(
    *,
    replayed_stages: tuple[str, ...],
    stage_outcomes: dict[str, Any],
) -> dict[str, Any]:
    """Validate that only stages that actually ran are replayed."""
    if type(replayed_stages) is not tuple:
        return dict(
            reconciled=False,
            reason="REPLAYED_STAGES_TUPLE_REQUIRED",
            violations=["REPLAYED_STAGES_TUPLE_REQUIRED"],
        )
    if type(stage_outcomes) is not dict:
        return dict(
            reconciled=False,
            reason="STAGE_OUTCOMES_DICT_REQUIRED",
            violations=["STAGE_OUTCOMES_DICT_REQUIRED"],
        )

    violations: list[str] = []

    # Check replayed stages are a subset of RAN_STAGES (not NOT_RUN_STAGES)
    for stage in replayed_stages:
        if stage in NOT_RUN_STAGES:
            violations.append(f"NOT_RUN_STAGE_REPLAYED:{stage}")
        elif stage not in RAN_STAGES:
            violations.append(f"UNKNOWN_STAGE_REPLAYED:{stage}")

    # Check stage_outcomes only has keys for RAN_STAGES
    for stage in stage_outcomes:
        if stage in NOT_RUN_STAGES:
            violations.append(f"NOT_RUN_STAGE_OUTCOME_PRESENT:{stage}")
        elif stage not in RAN_STAGES:
            violations.append(f"UNKNOWN_STAGE_OUTCOME_PRESENT:{stage}")

    reconciled = not violations
    return dict(
        reconciled=reconciled,
        reason="REFUSAL_REPLAY_RECONCILED" if reconciled else "REFUSAL_REPLAY_VIOLATIONS",
        violations=violations,
    )
