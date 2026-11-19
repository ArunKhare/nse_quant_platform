# Cash-stock swing strategy

`src/nse_quant/strategy/cash_stock_swing.py` is a proposal-only cash-stock swing
strategy, consistent with the Trading Universe Roadmap Phase 2.

## Contract

- Input: daily candles list (date, open, high, low, close, volume) plus optional
  `event_risk_active`.
- Output: `TradeProposal` with entry/stop/target/time-stop, plus gate results.
- Entry rule: SMA50 > SMA200, close > prior 20-day high, RVOL >= threshold, and
  no active event risk.
- Stop: entry - 2 x ATR14; target: entry + 2R; time stop: 10 trading days.
- RVOL: current volume divided by the mean of the PRIOR baseline_periods rows
  (excluding current), avoiding look-ahead.

## Safety

- Proposal-only; never submits, modifies, or cancels an order.
- Paper-mode ready; inherits the persistent kill switch, dry-run behavior,
  data-quality checks, liquidity checks, and risk controls.
- Event filter blocks entry when `event_risk_active=True`.
