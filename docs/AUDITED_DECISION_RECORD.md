# Actual audited native strategy/risk decision record

`audit_decision` produces an audited decision record with a fingerprint for a strategy or portfolio-risk decision, without granting eligibility or enabling live trading.

## Contract

- Input: `DecisionRecord` (stage, inputs, outcome).
- Output: `AuditedDecision` with stage, fingerprint, recorded, reason, decision_eligibility_asserted (always False).
- Safety: never grants eligibility, never enables live trading.

## Rules

- Supports only "strategy" and "portfolio_risk" stages.
- Fingerprint is deterministic SHA-256 over canonical (stage, inputs, outcome).
- Refuses unsupported stage, invalid record.
- Addresses the "actual audited native strategy/risk decisions" sub-gap of gate 6 from docs/CURRENT_NATIVE_STATUS.md.
