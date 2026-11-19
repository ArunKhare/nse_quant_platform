# Stock-option liquidity thresholds

`src/nse_quant/research/stock_option_liquidity.py` is a pure additive research evaluator for stock-option liquidity (spread, depth, OI, volume), consistent with the Trading Universe Roadmap Phase 3.

## Contract

- `evaluate_liquidity(bid, ask, depth, open_interest, volume, settings)` returns a dict with `tradable`, `spread_pct`, `failures`, settings echo, and `decision_eligibility_asserted=False`.
- `classify_liquidity(result)` returns `LIQUID`, `MARGINAL`, or `ILLIQUID`.

## Safety

- Research evaluator only; no execution authority, no admission, no decision eligibility.
- `decision_eligibility_asserted=False` on every result.
- Liquidity classification is observational; it does not grant or gate anything.
