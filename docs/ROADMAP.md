# Roadmap

## Milestone 1 — Paper decision loop

**Status: Core live decision loop complete; FS4 complete; FS5 reliability evidence active.**

### Completed

- Dynamic NIFTY chain discovery.
- Unified option-stream schema.
- IV/Greeks, IV rank, RV, OI/PCR, liquidity, and regime research.
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
- MFT evidence persistence and daily evidence health reporting.
- IV analytics diagnostics: current IV, history bounds, valid observation count,
  IV rank, percentile, and calculation version.
- Per-leg iron-condor entry-premium persistence.
- Net-credit strategy marking and leg-level unrealized P&L reconciliation.
- Stale option-mark persistence, cycle-level reporting, and stale-mark alert events.
- Replay/live decision parity checks.
- Removed the redundant post-proposal regime-policy gate.
- End-to-end paper-order proposal, fill, position, marking, exit, and
  post-trade-review validation.
- Kill-switch order-block validation.
- FS4 availability-aware Gold feature retrieval.
- FS4 lineage-pinned decision bundles.
- FS4 exact replay.
- FS4 QA and tests passed.

## FS5 — Multi-day paper-loop reliability evidence

**Status: Active.**

### Objective

Run the existing NIFTY iron-condor paper decision loop reliably across multiple
complete NSE trading days and retain auditable evidence for every stage.

### Scope

- Run the paper loop across multiple complete trading days.
- Persist daily snapshots, feature availability, proposals, gates, paper orders,
  fills, positions, marks, exits, and post-trade reviews.
- Validate Gold retrieval and exact replay during live-loop operation.
- Treat unavailable or stale inputs as unavailable or blocked; do not fill gaps.
- Track failures by capture, Silver, Gold, retrieval, feature, gate, order,
  persistence, and review category.
- Produce daily reliability reports and a final multi-day closure report.
- Preserve `decision_eligibility_asserted=false`; do not assert trading authority.

### Acceptance criteria

- Multiple complete trading days run without unrecovered loop failure.
- Gold retrieval and replay remain stable during operation.
- Missing or invalid data blocks or marks features unavailable.
- Paper-order lifecycle remains stable.
- Persistent kill switch continues to halt the loop.
- Daily evidence health is reportable and persisted.
- Decision eligibility remains false and live trading remains disabled.

### Deliverable

- `output/fs5-paper-loop-reliability.zip`

### Remaining for full Milestone 1 closure

- Complete FS5 multi-day paper-loop reliability evidence.

## Milestone 2 — Research depth

### Completed

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
- Vectorbt research-only backtest adapter.
- Deterministic vectorbt backtesting.
- Real-price completed-trade vectorbt replay.
- Vectorbt backtest tests.
- Iron-condor historical backtester.
- Backtest CLI.
- Backtest readiness checks.
- Walk-forward reporting.
- Integrate iron-condor trade output with vectorbt backtesting.
- Add multi-leg vectorbt portfolio modeling.
- Connect walk-forward experiments to vectorbt evaluation.
- Add vectorbt CLI integration.
- Add regime-level vectorbt reporting.
- Add deterministic vectorbt run manifests.

### Remaining

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

## References

- `docs/PLATFORM_DISCUSSION_DECISION_RECORD.md`