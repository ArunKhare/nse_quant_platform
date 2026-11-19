# Refusal-to-audited-record integration

`build_audited_record_from_refusal` takes the refusal decision's `result` dict and produces an `AuditedDecision` via `audited_decision_record.audit_decision`.

## Contract

- Input: refusal_result dict (the refusal decision's `result` field).
- Output: AuditedDecision with stage, fingerprint, recorded, reason, decision_eligibility_asserted.
- Safety: never grants eligibility, never enables live trading.

## Rules

- Stage defaults to "strategy" if `failed_stage` is absent or not in ("strategy", "portfolio_risk").
- Inputs built from stage_trace, input_requirements_version, input_requirements_sha256, input_inventory, inventory_scope, safety_observation_origin, admission_observed.
- Outcome built from status, failed_stage, reason_codes, strategy_evaluated, portfolio_risk_evaluated, execution_attempted, order_emitted, decision_eligibility_asserted, complete_strategy_replay_asserted.
- Refuses non-dict refusal_result.
- Addresses the "actual audited native strategy/risk decisions" sub-gap of gate 6 from docs/CURRENT_NATIVE_STATUS.md.
