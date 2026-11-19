# Stock-option defined-risk strategies

`src/nse_quant/research/stock_option_defined_risk.py` is a pure additive research evaluator for stock-option defined-risk strategies (bull call spread, bear put spread, iron condor, iron fly), consistent with the Trading Universe Roadmap Phase 3.

## Contract

- `evaluate_bull_call_spread(long_strike, short_strike, long_premium, short_premium, settings)` returns a dict with `valid`, `wing_width`, `net_debit`, `max_profit`, `max_loss`, `risk_reward_ratio`, `failures`, and `decision_eligibility_asserted=False`.
- `evaluate_bear_put_spread(...)` same shape for bear put spread.
- `evaluate_iron_condor(put_long_strike, put_short_strike, call_short_strike, call_long_strike, net_credit, settings)` returns a dict with `valid`, `put_wing_width`, `call_wing_width`, `net_credit`, `max_loss`, `failures`, and `decision_eligibility_asserted=False`.
- `evaluate_iron_fly(put_long_strike, center_strike, call_long_strike, net_credit, settings)` same shape for iron fly.

## Safety

- Research evaluator only; no execution authority, no admission, no decision eligibility.
- `decision_eligibility_asserted=False` on every result.
- Structure validation is observational; it does not grant or gate anything.
