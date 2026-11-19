# Cash-stock swing strategy signal generator

`src/nse_quant/research/cash_stock_swing.py` is a pure additive research signal generator for a cash-stock swing strategy, consistent with the Trading Universe Roadmap Phase 2.

## Contract

- Input: daily candles DataFrame (date, open, high, low, close, volume, sorted ascending) plus optional `CashStockSwingSettings` and `event_risk_active`.
- Output: signal dict with entry/stop/target/time-stop/event-filter, component flags, and `decision_eligibility_asserted=False`.
- Entry rule: SMA50 > SMA200, close > prior 20-day high, RVOL >= threshold, and no active event risk.
- Stop: entry - 2 x ATR14; target: entry + 2R; time stop: 10 trading days.
- RVOL: current volume divided by the mean of the PRIOR baseline_periods rows (excluding current), avoiding look-ahead.

## Safety

- Research signal generator only; no order placement, no execution authority, no admission, no decision eligibility.
- `decision_eligibility_asserted=False` on every result.
- Event filter blocks entry when `event_risk_active=True`; it does not grant eligibility.
