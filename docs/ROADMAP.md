# Roadmap

## Milestone 1 — Paper decision loop

**Status: Core live decision loop complete; closure validation in progress.**

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
- MFT evidence persistence and daily evidence health reporting.
- IV analytics diagnostics: current IV, history bounds, valid observation count, IV rank, percentile, and calculation version.
- Per-leg iron-condor entry-premium persistence.
- Net-credit strategy marking and leg-level unrealized P&L reconciliation.
- Stale option-mark persistence, cycle-level reporting, and stale-mark alert events.
- Replay/live decision parity checks.
- Removed the redundant post-proposal regime-policy gate.
- End-to-end paper-order proposal, fill, position, marking, exit, and post-trade-review validation.
- Kill-switch order-block validation.
- FS4 availability-aware Gold feature retrieval, lineage-pinned decision bundles, and exact replay.
- FS4 QA and tests passed.

## FS5 — Multi-day paper-loop reliability evidence

**Status: Active.**

Objective:

Run the existing NIFTY iron-condor paper decision loop reliably across multiple
complete NSE trading days and retain auditable evidence for every stage.

Scope:

- Run the paper loop across multiple complete trading days.
- Persist daily snapshots, feature availability, proposals, gates, paper orders,
  fills, positions, marks, exits, and post-trade reviews.
- Validate Gold retrieval and exact replay during live-loop operation.
- Treat unavailable or stale inputs as unavailable or blocked; do not fill gaps.
- Preserve `decision_eligibility_asserted=false`; do not assert trading authority.
- Track failures by capture, Silver, Gold, retrieval, feature, gate, order,
  persistence, and review category.
- Produce daily reliability reports and a final multi-day closure report.

Acceptance criteria:

- Multiple complete trading days run without unrecovered loop failure.
- Gold retrieval and replay remain stable during operation.
- Missing or invalid data blocks or marks features unavailable.
- Paper-order lifecycle remains stable.
- Persistent kill switch continues to halt the loop.
- Daily evidence health is reportable and persisted.
- Decision eligibility remains false and live trading remains disabled.

Deliverable:

- `output/fs5-paper-loop-reliability.zip`

## Remaining for full Milestone 1 closure

- Complete FS5 multi-day paper-loop reliability evidence.

## Milestone 2 — Research depth

Completed:

- Historical Parquet warehouse.
- Warehouse validation and research-grade day selection.
- IV surface, daily IV, IV regime, and RV regime research.
- Replay-based iron-condor backtest harness.
- Deterministic exit-lifecycle coverage.
- QuantStats equity-curve reporting and performance summaries.
- Paper-only strategy parameter experiments.
- Experiment ranking, exit-reason analysis, and promotion gating.
- Cash-stock swing strategy signal generator (research-only, look-ahead-safe RVOL).
- Corporate-actions and earnings calendar (research-only registry).
- Stock-option liquidity thresholds (research-only evaluator).
- Stock-option event-risk rules (research-only evaluator).
- Stock-option defined-risk strategies (research-only structure validator).
- Stock-option execution quality (research-only evaluator).
- Stock-option paper strategy launch readiness (research-only evaluator).
- Cash-stock swing strategy promoted to `src/nse_quant/strategy/cash_stock_swing.py` (proposal-producing, paper-mode ready).
- Native authority-evidence completeness-report audit-trail policy and replay.
- Native authority-evidence completeness-report audit-trail final audit and replay.
- Native authority-evidence completeness-report audit-trail enforcement and replay.
- Native authority-evidence completeness-report audit-trail persistence and replay.
- Native authority-evidence completeness-report audit-trail retention and expiry governance.
- Native authority-evidence completeness-report audit-trail archival and closure governance.
- Native authority-evidence completeness-report audit-trail query and export governance.
- Native authority-evidence completeness-report audit-trail import, round-trip, acceptance, and reconciliation governance.
- Native authority-evidence completeness-report audit-trail end-to-end lifecycle acceptance.
- Native authoritative availability and economic-validity evidence.

Remaining:

- Retention and expiry governance for persisted audit trails.
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
- Stocks
- Directional defined-risk debit/credit spreads.
- Multi-leg strategy library.

- [Future Implementation Configuration](docs/FUTURE_IMPLEMENTATION.md)


- `docs\PLATFORM_DISCUSSION_DECISION_RECORD.md` - detailed, source-grounded record of
  our architecture and implementation discussion, including the legacy loop,
  Medallion path, P0–P5 status, configuration design, analytics/research overlap,
  dashboard scope, safety boundaries, and operational holds.
