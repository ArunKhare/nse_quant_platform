# Stock-option paper strategy launch readiness

`src/nse_quant/research/stock_option_launch_readiness.py` is a pure additive research evaluator that combines liquidity, event-risk, defined-risk structure, and execution quality into a single paper-mode launch readiness check, consistent with the Trading Universe Roadmap Phase 3.

## Contract

- `evaluate_launch_readiness(liquidity_result, event_risk_result, defined_risk_result, execution_quality_result, settings)` returns a dict with `ready`, `checks`, `failures`, settings echo, and `decision_eligibility_asserted=False`.
- `classify_launch_readiness(result)` returns `READY`, `CONDITIONAL`, or `NOT_READY`.

## Safety

- Research evaluator only; no execution authority, no admission, no decision eligibility.
- `decision_eligibility_asserted=False` on every result.
- Launch-readiness classification is observational; it does not grant or gate anything.
