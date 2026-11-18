# Current native-platform status

Status reconciliation: 2026-11-17. This document separates source inspection,
user-confirmed repository QA and supplied Git history. It is not an independent
inspection of the local Windows repository or an authority to release held work.

## Evidence basis

The user confirms that Sources represent the latest committed implementation and
that repository QA/tests passed, including the latest native-input package and
the regime-policy timestamp repair.
That confirmation is accepted; it is not assistant-reproduced repository QA.

## Native architecture and existing boundaries

Received artifacts -> immutable Bronze -> typed source-linked Silver -> versioned
Gold -> published bundles -> native decisions and exact replay.

Legacy option_stream mixes observations and analytics; it is not native Bronze.
Provider tokens, symbols, labels and self-hashes are not canonical identities.
Unknown provenance and source times remain unknown. Build native services rather
than extending transitional legacy adapters.

## Recent additive research modules

The following pure additive research evaluators/generators were delivered and
user-QA-confirmed. They are observational only and do not grant decision
eligibility, execution authority, or close any status gate.

- Cash-stock swing strategy signal generator (`src/nse_quant/research/cash_stock_swing.py`): SMA/breakout/RVOL/ATR entry with event filter; `compute_rvol` uses a shift(1) baseline to avoid look-ahead.
- Corporate-actions and earnings calendar (`src/nse_quant/research/corporate_actions_calendar.py`): blackout and upcoming-event research registry.
- Stock-option liquidity thresholds (`src/nse_quant/research/stock_option_liquidity.py`): spread/depth/OI/volume tradability evaluator.
- Stock-option event-risk rules (`src/nse_quant/research/stock_option_event_risk.py`): earnings blackout, size reduction, short-volatility block evaluator.
- Stock-option defined-risk strategies (`src/nse_quant/research/stock_option_defined_risk.py`): bull call spread, bear put spread, iron condor, iron fly structure validator.
- Stock-option execution quality (`src/nse_quant/research/stock_option_execution_quality.py`): quote age, spread, depth, risk-reward, slippage, time-to-event evaluator.
- Stock-option paper strategy launch readiness (`src/nse_quant/research/stock_option_launch_readiness.py`): combines liquidity, event risk, defined-risk validity, and execution quality into a single launch-readiness check.

All of these return `decision_eligibility_asserted=False` and are research-only.

## Regime-policy timestamp repair

`save_regime_policy` in `src/nse_quant/persistence/duckdb_store.py` was repaired
so that `risk_limits` JSON is written to the `risk_limits` JSON column and
`datetime.now(UTC)` is written to the `created_at` TIMESTAMPTZ column, matching
the actual DDL column order. The matching Bronze test
`tests/data_platform/test_legacy_regime_policies_bronze.py` retains index-9
assertions for `risk_limits`, consistent with the DDL. User QA and tests passed.

## 2026-11-17 native-platform increments

The following native-platform increments are implemented and user-QA-confirmed.
They remain observational and do not close any native status gate, grant
decision eligibility, authorize live trading, or authorize healing, backfill,
adoption, or execution.

- Native option-chain snapshot Bronze and Silver.
- Persisted audited decision-run coverage reconciliation Silver.
- End-to-end native iron-condor decision-run pipeline.
- Authoritative identity and time boundary validation.
- Coverage evidence-link validation.
- Decision-loop integration with evidence links.
- Reconciliation evidence-completeness validation.
- End-to-end Gate 6 acceptance tests.
- Availability and economic-validity evidence validation.
- Gold decision publication candidate validation.
- Eligible admission contract evaluation.
- Lifecycle-recovery observations.
- Operational acceptance harness.
- Controlled execution gateway with paper-only default behavior.
- Multi-underlying expansion validation for NIFTY and BANKNIFTY.
- Native authority-evidence completeness-report audit-trail policy and replay.
- Native authority-evidence completeness-report audit-trail final audit and replay.
- Native authority-evidence completeness-report audit-trail enforcement and replay.
- Native authority-evidence completeness-report audit-trail persistence and replay.
- Native authority-evidence completeness-report audit-trail retention and expiry governance.
- Native authority-evidence completeness-report audit-trail archival and closure governance.
- Native authority-evidence completeness-report audit-trail query and export governance.
- Native authority-evidence completeness-report audit-trail import, round-trip, acceptance, and reconciliation governance.
- Native authoritative identity, derivative binding, and authorized revocation evidence.
- Native authoritative availability and economic-validity evidence.
- Native authoritative evidence acceptance and reconciliation.
- Native authoritative evidence decision-loop linkage.
- Native authoritative evidence real accepted-authority integration.
- Native authoritative evidence completeness-report integration.
- Native authoritative evidence completeness-report audit-trail integration.
- Native authoritative evidence final-audit integration.
- Native authoritative evidence chain end-to-end validation.
- Native authoritative evidence platform acceptance verification.

`authoritative_identity_and_time` remains explicitly unmapped and is never
auto-coverable. `POINT_IN_TIME_DECISION` remains rejected before recording,
replay, publication, admission, or execution.

## Remaining gates

1. Independently authenticated governance/namespace authority and real lifecycle
   evidence, not merely possession of a supplied signing key/root.
2. Authoritative underlying identity, derivative binding and authorized revocation.
3. Independently evidenced availability and economic validity; knowledge_cutoff
   and economic_at remain separate axes.
4. A NEW sufficient eligible publication/admission contract. Existing research
   @1 must still reject POINT_IN_TIME_DECISION; candidates do not promote it.
5. Research lifecycle/recovery beyond bounded first-write profiles without healing
   original failed, incomplete, unlinked or orphan obligations by later success.
6. Complete required native strategy/analytics inputs, actual audited native
   strategy/risk decisions and complete exact replay of stages that actually run.
   Reconcile uncovered inputs against the accepted current candidate first.
7. Full integrated and operational acceptance. Package QA is not platform acceptance.

No new failure is reported. Do not reopen historical closed regressions, invent a
completion percentage or interpret legacy 'no blockers' as native admission readiness.

## Holds and operational policy

Data loading/migration remains held. No live acquisition, user-data migration or
backfill, real identity/key/policy/authority registration, production publication,
trading or decision-loop cutover is authorized. Disposable synthetic fixtures are
allowed. No allow-unknown, force-eligible or caller verification boolean bypass.

scripts/qa was intentionally deleted by the user. Do not recreate it or rely on
historical runner references. Run QA commands directly when repository execution
is available, checking the actual uv-selected interpreter rather than prompt labels:

    uv run python -c "import sys; print(sys.executable); print(sys.version)"
    uv run pytest tests/data_platform -q
    uv run pytest tests -q
    uv run ruff check src/nse_quant/data_platform scripts/inspect scripts/ingest tests/data_platform
    uv run mypy
    git diff --check

Check untracked additions for whitespace separately; git diff --check does not
cover them. Do not auto-stage, clean, discard or delete runtime logs.

## Verification attribution

- User-confirmed repository QA: accepted, including the native-input package and
  the regime-policy timestamp repair.
- Supplied Git history: retained above, not independently verified locally.
- Historical assistant sandbox checks: keep original attribution and scope.
