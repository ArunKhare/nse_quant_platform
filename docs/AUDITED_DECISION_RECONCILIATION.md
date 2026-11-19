# Audited decision reconciliation

`reconcile_audited_decision` validates that the refusal decision's stage trace correctly marks strategy/risk/execution as NOT_RUN (not fabricated), matching the refusal-only contract in `native_refusal_decision.py`.

## Contract

- Input: decision_result dict (the refusal decision's `result` field).
- Output: dict with reconciled, reason, violations (list of issue codes).
- Safety: never grants eligibility, never enables live trading.

## Rules

- Stage trace must be a list with correct order matching EXPECTED_STAGES.
- NOT_RUN stages (strategy, portfolio_risk, execution) must be marked NOT_RUN.
- Non-NOT_RUN stages must not be marked NOT_RUN.
- Flags `strategy_evaluated`, `portfolio_risk_evaluated`, `execution_attempted`, `order_emitted` must be False.
- `decision_eligibility_asserted` and `complete_strategy_replay_asserted` must be False.
- Refuses non-dict decision_result.
- Addresses the "actual audited native strategy/risk decisions" sub-gap of gate 6 from docs/CURRENT_NATIVE_STATUS.md.
