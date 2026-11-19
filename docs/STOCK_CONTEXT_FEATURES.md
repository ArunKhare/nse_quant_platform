# Stock context features

`src/nse_quant/research/stock_context_features.py` is a pure additive research calculator for stock-level context features (beta, correlation, relative strength, sector regime, market breadth), consistent with the Trading Universe Roadmap Phase 2/5.

## Contract

- `compute_beta(stock_returns, benchmark_returns, window=...)` returns beta or None if insufficient data.
- `compute_correlation(...)` returns correlation or None.
- `compute_relative_strength(...)` returns cumulative return difference or None.
- `classify_sector_regime(relative_strength)` returns OUTPERFORMING/UNDERPERFORMING/NEUTRAL or None.
- `compute_market_breadth(advancing, declining)` returns breadth ratio or None.
- `build_context_features(...)` returns the full payload with `decision_eligibility_asserted=False`.

## Safety

- Research calculator only; no execution authority, no admission, no decision eligibility.
- `decision_eligibility_asserted=False` on every result.
- Beta and relative strength are observational features, not hard entry gates.
