## Current sprint

# FS5 — Multi-day paper-loop reliability evidence

For current native-platform status, evidence attribution, remaining gates and
operational holds, see [CURRENT_NATIVE_STATUS.md](CURRENT_NATIVE_STATUS.md).

FS4 is complete: availability-aware Gold feature retrieval, lineage-pinned
decision bundles, and exact replay are implemented. Repository QA and tests
passed.

The active sprint is FS5: run the NIFTY iron-condor paper decision loop
reliably across multiple complete NSE trading days and retain auditable
evidence for every stage.

### Objective

Complete Milestone 1 closure by demonstrating reliable multi-day paper-loop
operation with complete evidence, stable Gold retrieval/replay, and unchanged
safety boundaries.

### Scope

- [ ] Run the paper loop across multiple complete trading days.
- [ ] Persist daily snapshots, feature availability, proposals, gates, paper
      orders, fills, positions, marks, exits, and post-trade reviews.
- [ ] Validate Gold retrieval and exact replay during live-loop operation.
- [ ] Treat unavailable or stale inputs as unavailable or blocked; do not fill gaps.
- [ ] Track failures by capture, Silver, Gold, retrieval, feature, gate, order,
      persistence, and review category.
- [ ] Produce daily reliability reports.
- [ ] Produce a final multi-day closure report.
- [ ] Preserve `decision_eligibility_asserted=false`.
- [ ] Keep live trading disabled.


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
- FS4 availability-aware Gold feature retrieval.
- FS4 lineage-pinned decision bundles.
- FS4 exact Gold replay.
- FS4 QA and tests passed.
- Milestone 2 parameter-experiment harness.
- Experiment exit-reason tracking and analysis.
- QuantStats backtest reporting.
- Telegram operational test and lifecycle notifications.

## Next sprint candidates

1. `FS5 multi-day paper-loop reliability evidence` — active Milestone 1 closure work.
2. `Walk-forward parameter` validation — completed; retain only for follow-up validation or extension.
3. `event_risk` evidence plugin — implemented; requires operational acceptance evidence.
4. `technical_indicators` evidence plugin — implemented; requires operational acceptance evidence.
5. `volume_flow` evidence plugin — implemented; requires operational acceptance evidence.
6. `option_positioning` evidence plugin — implemented; requires operational acceptance evidence.
7. Event-to-instrument impact mapping — implemented; requires operational acceptance evidence.
8. Multi-horizon NIFTY strategy profiles — implemented; requires operational acceptance evidence.


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

Notes:
- Implement liquidity-aware long wings	Permanent production-quality improvement
- Restore min_iv_rank: 40 later	Once you have 20–60 days of option-chain history
- using Views to populate the Dashboards