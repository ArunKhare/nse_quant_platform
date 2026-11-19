# Strategy evaluation integration

`integrate_strategy_evaluation` combines the outputs of the existing gates (MarketOpenGate, IvRegimeGate, ExpectedMoveGate, LiquidityGate) plus analytics validation plus portfolio risk into a single audited strategy decision.

## Contract

- Input: `GateOutputs` (market_session_passed, iv_regime_passed, expected_move_passed, liquidity_passed), `AnalyticsOutcome` (valid), `PortfolioRiskOutcome` (approved).
- Output: `IntegratedDecision` with approved, reasons, checks, decision_eligibility_asserted (always False).
- Safety: never grants eligibility, never enables live trading.

## Rules

- Approved only when all 6 checks pass.
- Refuses invalid inputs.
- Addresses the "strategy evaluation integration" sub-gap of gate 6 from docs/CURRENT_NATIVE_STATUS.md.
