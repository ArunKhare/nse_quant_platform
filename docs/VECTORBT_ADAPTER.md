# vectorbt backtest adapter

`src/nse_quant/research/backtest/vectorbt_adapter.py` is a pure additive research-only bridge from the existing `BacktestResult.equity_curve` (or a trade list) to a vectorbt `Portfolio`, returning research metrics (total return, max drawdown, Sharpe).

## Contract

- `equity_curve_to_series(equity_curve)` converts the equity-curve list into a pandas Series indexed by ts.
- `run_vectorbt_from_equity_curve(equity_curve=..., settings=...)` builds a vectorbt Portfolio from the equity curve and returns total_return, max_drawdown, sharpe_ratio, and `decision_eligibility_asserted=False`.
- `run_vectorbt_from_trades(trades=..., settings=...)` builds a vectorbt Portfolio from a trade list (entry_ts, exit_ts, size, entry_price, exit_price) and returns the same metric shape.

## Safety

- Research-only adapter; no order placement, no execution authority, no admission, no decision eligibility.
- `decision_eligibility_asserted=False` on every result.
- vectorbt is already a declared dependency in pyproject.toml (vectorbt>=0.26.0), so no new dependency is introduced.
