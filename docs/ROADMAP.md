# Roadmap

## Milestone 1 — Paper decision loop

**Status: Core live decision loop complete (V0.21.0).**

Completed:

- Dynamic NIFTY chain discovery.
- Unified option-stream schema.
- IV/Greeks, IV rank, RV, OI/PCR, liquidity, regime.
- Live 1m spot-candle capture and live spot-feature refresh.
- Real rolling 1m close history for realized volatility and intraday regime.
- Invalid realized-volatility guard: missing or zero RV is treated as unavailable.
- Live snapshot and status observability without querying DuckDB during loop operation.
- Pre-trade gates.
- Iron-condor monitor.
- Policy-gated paper decisioning; `BEAR|HIGH` correctly blocks iron condors.
- Paper orders, positions, P&L, and review.
- Dash console.
- Tests.

Remaining for full Milestone 1 closure:

- End-to-end paper-order proposal, fill, position, and exit validation.
- Kill-switch order-block validation.
- Replay/live decision parity checks.

## Milestone 2 — Research depth

- Historical Parquet warehouse.
- Backtests with vectorbt.
- QuantStats reports.
- Strategy parameter experiments.
- IV surface and term-structure research.

## Milestone 3 — Controlled execution

- Kite order placement behind an explicit, separately enabled configuration.
- Order reconciliation.
- Margin checks.
- Partial-fill handling.
- Rule-based exits and post-trade thesis monitoring.

## Milestone 4 — Expansion

- BANKNIFTY.
- Stock options.
- Stocks
- Directional defined-risk debit/credit spreads.
- Multi-leg strategy library.

- [Future Implementation Configuration](docs/FUTURE_IMPLEMENTATION.md)