# Roadmap (updated)

## Milestone 1 — Paper decision loop

Remaining for full Milestone 1 closure:
- Run the paper loop reliably across multiple complete trading days.

## Milestone 2 — Research depth

Completed (added): walk-forward experiment validation.

Remaining:
- Backtests with vectorbt.
- Multi-complete-trading-day reliability evidence.

## Milestone 3 — Controlled execution

- Kite order placement behind an explicit, separately enabled configuration.
- Order reconciliation.
- Margin checks.
- Partial-fill handling.
- Rule-based exits and post-trade thesis monitoring.

## Milestone 4 — Expansion

- BANKNIFTY.
- Stock options.
- Stocks.
- Directional defined-risk debit/credit spreads.
- Multi-leg strategy library.

- `docs\PLATFORM_DISCUSSION_DECISION_RECORD.md` - detailed, source-grounded record of
  our architecture and implementation discussion, including the legacy loop,
  Medallion path, P0–P5 status, configuration design, analytics/research overlap,
  dashboard scope, safety boundaries, and operational holds.