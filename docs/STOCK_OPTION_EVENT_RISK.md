# Stock-option event-risk rules

`src/nse_quant/research/stock_option_event_risk.py` is a pure additive research evaluator for stock-option event risk (earnings blackout, size reduction, short-volatility block), consistent with the Trading Universe Roadmap Phase 3.

## Contract

- `evaluate_event_risk(event_date, as_of_date, days_to_event, days_since_event, settings)` returns a dict with `block_new_entry`, `reduce_size`, `size_reduction_factor`, `actions`, `failures`, settings echo, and `decision_eligibility_asserted=False`.

## Safety

- Research evaluator only; no execution authority, no admission, no decision eligibility.
- `decision_eligibility_asserted=False` on every result.
- Event-risk classification is observational; it does not grant or gate anything.
