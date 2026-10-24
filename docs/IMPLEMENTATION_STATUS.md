## Current sprint

### Objective

Complete Milestone 1 closure validation and harden the evidence, valuation,
and observability foundation.

### Scope

- [x] MFT evidence plugin and decision-loop integration
- [x] `decision_evidence` persistence
- [x] Evidence availability, failure, and completeness reporting
- [x] IV analytics diagnostics and validated IV-rank eligibility checks
- [x] Per-leg iron-condor entry-premium persistence
- [x] Net-credit strategy valuation and leg-level P&L reconciliation
- [x] Stale option-mark persistence and alert events
- [ ] End-to-end paper-order proposal, fill, position, marking, exit, and post-trade-review validation
- [ ] Kill-switch order-block validation
- [ ] Replay/live decision parity checks
- [ ] Multi-complete-trading-day paper-loop reliability run
- [ ] Remove redundant post-proposal regime-policy gate

## Completed

- NIFTY paper decision loop.
- Persistent kill switch.
- Paper-only execution boundary.
- Live NIFTY 1-minute candle capture.
- NIFTY option-chain and IV observation capture.
- Daily RV build process.
- IV regime classification.
- Regime-aware iron-condor eligibility.
- `iron_condor_monitor` strategy profile.
- EOD maintenance.
- Option-stream Parquet export.
- Warehouse validation.
- MFT evidence plugin foundation and `decision_evidence` persistence.
- Daily evidence availability, failure, and completeness reporting.
- IV analytics diagnostics with calculation-version traceability.
- Per-leg iron-condor premium persistence.
- Net-credit strategy marking and leg-level P&L reconciliation.
- Stale option-mark tracking, persistence, and alert events.

## Next sprint candidates

1. `event_risk` evidence plugin.
2. `technical_indicators` evidence plugin.
3. `volume_flow` evidence plugin.
4. `option_positioning` evidence plugin.
5. Event-to-instrument impact mapping.
6. Multi-horizon NIFTY strategy profiles.

## Acceptance criteria for Stage 2

Stage 2 is complete when:

- MFT evidence is persisted for every paper decision cycle.
- 15m and 60m evidence is derived only from completed 1m candles.
- Partial higher-timeframe buckets are excluded.
- Insufficient data results in `available=false`, not a loop failure.
- Plugin exceptions are caught and persisted as unavailable evidence.
- The persistent kill switch still halts the loop.
- Live trading remains disabled.
- The redundant post-proposal regime gate is removed.
- All tests pass.
- The paper loop has run reliably across multiple complete trading days.

## Blockers

None currently.

## Operational guardrails

These remain mandatory across all stages:

- Paper-only mode.
- Dry-run behavior.
- Persistent kill switch.
- Market-hours enforcement.
- Data-quality gates.
- Liquidity gates.
- Strategy risk limits.
- Portfolio risk limits.
- EOD review and warehouse exports.

## Update policy

Update this document when:

- A sprint starts or completes.
- A stage changes.
- A major feature is completed.
- A blocker is introduced or resolved.
- Acceptance criteria change.

Do not place detailed implementation instructions here. Use the relevant design
document instead.

- [Future Implementation Configuration](docs/FUTURE_IMPLEMENTATION.md)
