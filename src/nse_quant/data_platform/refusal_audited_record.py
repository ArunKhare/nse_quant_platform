"""Refusal-to-audited-record integration.

Takes the refusal decision's result dict and produces an AuditedDecision via
audited_decision_record.audit_decision, without granting eligibility or
enabling live trading. Addresses the "actual audited native strategy/risk
decisions" sub-gap of gate 6 from docs/CURRENT_NATIVE_STATUS.md.
"""

from __future__ import annotations

from typing import Any

from nse_quant.data_platform.audited_decision_record import (
    AuditedDecision,
    DecisionRecord,
    audit_decision,
)


def build_audited_record_from_refusal(
    *,
    refusal_result: dict[str, Any],
) -> AuditedDecision:
    """Build an AuditedDecision from the refusal decision's result dict."""
    if type(refusal_result) is not dict:
        return AuditedDecision(
            stage="unknown",
            fingerprint="",
            recorded=False,
            reason="REFUSAL_RESULT_OBJECT_REQUIRED",
        )

    # Extract stage from the refusal result (default to "strategy" if absent)
    stage = refusal_result.get("failed_stage", "strategy")
    if stage not in ("strategy", "portfolio_risk"):
        stage = "strategy"

    # Build inputs from the refusal result's relevant fields
    inputs = dict(
        stage_trace=refusal_result.get("stage_trace", []),
        input_requirements_version=refusal_result.get("input_requirements_version"),
        input_requirements_sha256=refusal_result.get("input_requirements_sha256"),
        input_inventory=refusal_result.get("input_inventory", []),
        inventory_scope=refusal_result.get("inventory_scope"),
        safety_observation_origin=refusal_result.get("safety_observation_origin"),
        admission_observed=refusal_result.get("admission_observed"),
    )

    # Build outcome from the refusal result's relevant fields
    outcome = dict(
        status=refusal_result.get("status"),
        failed_stage=refusal_result.get("failed_stage"),
        reason_codes=refusal_result.get("reason_codes", []),
        strategy_evaluated=refusal_result.get("strategy_evaluated", False),
        portfolio_risk_evaluated=refusal_result.get("portfolio_risk_evaluated", False),
        execution_attempted=refusal_result.get("execution_attempted", False),
        order_emitted=refusal_result.get("order_emitted", False),
        decision_eligibility_asserted=refusal_result.get("decision_eligibility_asserted", False),
        complete_strategy_replay_asserted=refusal_result.get(
            "complete_strategy_replay_asserted", False
        ),
    )

    record = DecisionRecord(
        stage=stage,
        inputs=inputs,
        outcome=outcome,
    )
    return audit_decision(record=record)
