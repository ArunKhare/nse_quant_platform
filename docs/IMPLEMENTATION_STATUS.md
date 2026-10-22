# Implementation Status

This is the operational status tracker for the NSE Quant Decision Platform.

It answers:

- What stage are we in?
- What is currently being implemented?
- What is complete?
- What is next?
- What must be true before moving to the next stage?

For long-term direction, see `ROADMAP.md`.
For instrument expansion, see `TRADING_UNIVERSE_ROADMAP.md`.
For event impact design, see `EVENT_IMPACT_SYNTHESIS.md`.

## Current stage

**Stage 2 — Evidence, event context, and NIFTY strategy expansion**

The NIFTY paper-loop foundation is operational. The current focus is to add
observational evidence plugins, event-risk context, and eventually additional
NIFTY strategies.

Live trading remains disabled.

## Stage progress

| Stage | Description | Status |
|---:|---|---|
| 1 | NIFTY paper-loop foundation | Complete |
| 2 | Evidence, event context, NIFTY strategy expansion | In progress |
| 3 | Multi-horizon NIFTY strategies | Not started |
| 4 | Cash-stock track | Not started |
| 5 | Stock-option track | Not started |
| 6 | Broader index context and beta | Not started |
| 7 | Additional index options | Not started |

## Current sprint

### Objective

Implement the MFT parallel-evidence plugin and establish the evidence-plugin
foundation.

### Scope

- [ ] `docs/MFT_PARALLEL_EVIDENCE.md`
- [ ] `src/nse_quant/research/candle_resampler.py`
- [ ] `src/nse_quant/research/evidence_plugins/__init__.py`
- [ ] `src/nse_quant/research/evidence_plugins/base.py`
- [ ] `src/nse_quant/research/evidence_plugins/registry.py`
- [ ] `src/nse_quant/research/evidence_plugins/multi_timeframe.py`
- [ ] `EvidenceSettings`
- [ ] `MultiTimeframeEvidenceSettings`
- [ ] `evidence` section in `config/settings.yaml`
- [ ] `decision_evidence` DuckDB table
- [ ] `DuckDBStore.write_decision_evidence()`
- [ ] `DuckDBStore.latest_spot_candles()`
- [ ] `DecisionLoop` integration
- [ ] Resampler tests
- [ ] Multi-timeframe plugin tests
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