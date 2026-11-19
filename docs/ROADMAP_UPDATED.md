# Roadmap (updated)

## Milestone 1 — Paper decision loop

Completed:

- Core NIFTY paper decision loop.
- Paper orders, positions, P&L, and review.
- Evidence persistence and daily evidence health reporting.
- Replay/live decision parity checks.
- Kill-switch order-block validation.
- FS4 availability-aware Gold feature retrieval, lineage-pinned decision bundles, and exact replay.
- FS4 QA and tests passed.

## FS5 — Multi-day paper-loop reliability evidence

**Status: Active.**

Remaining for full Milestone 1 closure:

- Run the paper loop reliably across multiple complete trading days.
- Persist daily evidence for snapshots, features, proposals, gates, orders,
  fills, positions, marks, exits, and reviews.
- Validate Gold retrieval and exact replay during operation.
- Produce daily reliability reports and a final multi-day closure report.
- Preserve `decision_eligibility_asserted=false`; do not authorize live trading.

## Milestone 2 — Research depth

Completed:

- Historical Parquet warehouse.
- Warehouse validation and research-grade day selection.
- IV surface, daily IV, IV regime, and RV regime research.
- Replay-based iron-condor backtest harness.
- Deterministic exit-lifecycle coverage.
- QuantStats equity-curve reporting and performance summaries.
- Paper-only strategy parameter experiments.
- Walk-forward experiment validation.
- Experiment ranking, exit-reason analysis, and promotion gating.
- Cash-stock swing strategy signal generator.
- Corporate-actions and earnings calendar.
- Stock-option liquidity, event-risk, defined-risk, execution-quality, and
  launch-readiness evaluators.
- Native authority-evidence completeness-report audit-trail lifecycle governance.
- Native authoritative availability and economic-validity evidence.

Remaining:

- Vectorbt research-only backtest adapter implemented.
- Backtests with vectorbt remain outstanding.
- FS5 multi-complete-trading-day reliability evidence.

## Native platform remaining gates

- Independent governance/namespace authority and real lifecycle evidence.
- Complete required native strategy/analytics inputs and operational acceptance.

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