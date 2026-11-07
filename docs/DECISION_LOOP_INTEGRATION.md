# Decision-loop integration

`run_decision_loop` combines strategy evaluation, audited decision record, and stage replay into a full decision-loop record.

## Contract

- Input: `DecisionLoopRequest` (gates, analytics, portfolio_risk, evaluators).
- Output: `DecisionLoopRecord` with integrated, audited, replayed, complete, reason, decision_eligibility_asserted (always False).
- Safety: never grants eligibility, never enables live trading.

## Rules

- Complete only when integrated.approved, audited.recorded, and all replayed outcomes match.
- Strategy replay inputs include gates, analytics, and portfolio risk so the recorded outcome can be re-derived from all of its dependencies.
- Refuses invalid request.
- Addresses the "decision-loop integration" sub-gap of gate 6 from docs/CURRENT_NATIVE_STATUS.md.
