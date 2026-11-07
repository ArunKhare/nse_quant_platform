"""Audited decision reconciliation for refusal-only native decisions.

Validates that the refusal decision's stage trace correctly marks
strategy/risk/execution as NOT_RUN (not fabricated), matching the refusal-only
contract in native_refusal_decision.py, without granting eligibility or
enabling live trading. Addresses the "actual audited native strategy/risk
decisions" sub-gap of gate 6 from docs/CURRENT_NATIVE_STATUS.md.
"""

from __future__ import annotations

from typing import Any

EXPECTED_STAGES = (
    "kill_switch",
    "safety_boundary",
    "publication_admission",
    "native_inputs",
    "strategy",
    "portfolio_risk",
    "execution",
)

NOT_RUN_STAGES = ("strategy", "portfolio_risk", "execution")


def reconcile_audited_decision(
    *,
    decision_result: dict[str, Any],
) -> dict[str, Any]:
    """Validate that the refusal decision's stage trace is correctly NOT_RUN."""
    if type(decision_result) is not dict:
        return dict(
            reconciled=False,
            reason="DECISION_RESULT_OBJECT_REQUIRED",
            violations=["DECISION_RESULT_OBJECT_REQUIRED"],
        )

    violations: list[str] = []

    # Check stage_trace exists and has correct structure
    trace = decision_result.get("stage_trace")
    if not isinstance(trace, list):
        violations.append("STAGE_TRACE_NOT_LIST")
    else:
        stages = [item.get("stage") for item in trace if isinstance(item, dict)]
        if stages != list(EXPECTED_STAGES):
            violations.append("STAGE_TRACE_ORDER_MISMATCH")
        else:
            # Check NOT_RUN stages are correctly marked
            for item in trace:
                if not isinstance(item, dict):
                    violations.append("STAGE_TRACE_ITEM_NOT_DICT")
                    continue
                stage = item.get("stage")
                status = item.get("status")
                if stage in NOT_RUN_STAGES and status != "NOT_RUN":
                    violations.append(f"NOT_RUN_STAGE_MARKED_{status}:{stage}")
                if stage not in NOT_RUN_STAGES and status == "NOT_RUN":
                    violations.append(f"NON_NOT_RUN_STAGE_MARKED_NOT_RUN:{stage}")

    # Check strategy/risk/execution flags are False
    for flag in (
        "strategy_evaluated",
        "portfolio_risk_evaluated",
        "execution_attempted",
        "order_emitted",
    ):
        if decision_result.get(flag) is not False:
            violations.append(f"FLAG_NOT_FALSE:{flag}")

    # Check decision_eligibility_asserted is False
    if decision_result.get("decision_eligibility_asserted") is not False:
        violations.append("DECISION_ELIGIBILITY_ASSERTED_NOT_FALSE")

    # Check complete_strategy_replay_asserted is False
    if decision_result.get("complete_strategy_replay_asserted") is not False:
        violations.append("COMPLETE_STRATEGY_REPLAY_ASSERTED_NOT_FALSE")

    reconciled = not violations
    return dict(
        reconciled=reconciled,
        reason="AUDITED_DECISION_RECONCILED" if reconciled else "AUDITED_DECISION_VIOLATIONS",
        violations=violations,
    )
