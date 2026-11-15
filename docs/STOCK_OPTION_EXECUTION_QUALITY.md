# Stock-option execution quality

`src/nse_quant/research/stock_option_execution_quality.py` is a pure additive research evaluator for stock-option execution quality (quote age, spread, depth, risk-reward, slippage, time-to-event), consistent with the Trading Universe Roadmap Phase 3.

## Contract

- `evaluate_execution_quality(quote_age_seconds, bid, ask, depth, risk_reward_ratio, expected_slippage_pct, time_to_event_days, settings)` returns a dict with `tradeable`, `spread_pct`, `failures`, settings echo, and `decision_eligibility_asserted=False`.
- `classify_execution_quality(result)` returns `GOOD`, `ACCEPTABLE`, or `POOR`.

## Safety

- Research evaluator only; no execution authority, no admission, no decision eligibility.
- `decision_eligibility_asserted=False` on every result.
- Execution-quality classification is observational; it does not grant or gate anything.
