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

## FS4 completion

FS4 delivered availability-aware Gold feature retrieval, lineage-pinned decision
bundles, and exact replay. The retrieval implementation returns the selected
Gold row’s feature revision ID; replay validates the bundle revision pin before
querying Gold.

Repository QA and tests passed. The completeness checker validates Gold feature
sets, observations, attempts, audit jobs, contracts, context hashes, lineage
pins, duplicate Silver revisions, and decision-eligibility assertions.

FS4 does not grant decision eligibility, publication authority, live acquisition
authority, or trading authority. `decision_eligibility_asserted` remains false.

## FS5 active sprint

FS5 is the active milestone: multi-complete-trading-day paper-loop reliability
evidence.

FS5 must run the existing NIFTY iron-condor paper decision loop across multiple
complete trading days, persist daily evidence, validate Gold retrieval and exact
replay during operation, and produce daily reliability reports plus a final
multi-day closure report.

FS5 remains paper-only. It must not authorize live acquisition, production
publication, decision eligibility, or trading.

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
- Native authoritative evidence release readiness verification.
- Native authoritative evidence production cutover readiness.
- Native authoritative evidence operational cutover authorization.
- Native authoritative evidence production cutover execution authorization.
- Native authoritative evidence production cutover execution readiness.
- Native authoritative evidence production cutover execution completion.
- Native P1 evidence-chain operational hardening.
- Native P1 evidence-chain operational hardening complete.
- Native P1 Gold/admission chain complete.
- Native P2 lifecycle/recovery complete.
- Native P3 operational acceptance complete.
- Native P4 controlled execution complete.
- Native P5 expansion complete.

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


`docs\PLATFORM_DISCUSSION_DECISION_RECORD.md`

## 2026-11-25 — S2 IV30 Gold candidate tranche

Implemented the audited, immutable observational India VIX IV30 Gold candidate
boundary in `src/nse_quant/data_platform/s2_iv30_gold.py`, with focused tests in
`tests/data_platform/test_s2_iv30_gold.py`. The writer recomputes the feature
from exact retained Bronze/VIX Silver/S2 materialization pins; the reader requires
an exact build pin, as-of availability, feature hash integrity and successful
original audit. Candidate persistence is not publication.

This closes only the bounded candidate persistence/retrieval implementation
step. It does NOT establish India VIX model suitability as the charter's
30-day constant-maturity option IV, wire the feature into `DecisionLoop`, alter
the VRP gate, grant decision eligibility, authorize live acquisition, or lift
existing publication and operational cutover holds. All such authority flags
remain false. The platform owner subsequently reported focused QA/tests passed;
this is owner-reported acceptance, not assistant-reproduced validation.


## 2026-11-27 — India VIX IV30 proxy suitability diagnostics

Added the pure research evaluator `src/nse_quant/research/india_vix_iv30_suitability.py`
and focused tests. It compares synchronized NIFTY India VIX observations with
the versioned `internal_cm` Black-76 30-day option-surface benchmark. It
validates source identity, revision/batch SHA-256 pin syntax, causal timestamps,
and a 30-second maximum source-time gap. It reports bias, MAE, RMSE, median/p90
absolute error, correlation, OLS slope/intercept, and chronological calibration
and holdout metrics.

The sample markers (60 matched pairs, 20 sessions, 20 holdout pairs) are minimum
evidence checks only, not suitability thresholds. Even sufficient data produces
`DIAGNOSTIC_ONLY_REVIEW_REQUIRED`, never approval. No empirical data is bundled;
durable option-surface evidence capture/replay remains outstanding. The evaluator
does not authenticate/replay its supplied source artifacts or establish historical
availability. It does not change the VRP evaluator, DecisionLoop, publication,
decision eligibility, acquisition, or trading authority. All authority flags
remain false. See `docs/INDIA_VIX_IV30_PROXY_SUITABILITY.md`.



## 2026-11-27 — native surface evidence acceptance boundary

Repository inspection found that durable observational surface recording was
already implemented in:

- `src/nse_quant/analytics/constant_maturity_inputs.py`
- `src/nse_quant/data_platform/surface_evidence_bundle.py`
- `src/nse_quant/data_platform/native_surface_recording.py`

The native recorder reads premiums only through exact native option-chain Bronze
pins, retains the reviewed calendar/forward/rate artifact bytes and calculation
policy with a content-addressed Silver variant, and recomputes the surface bundle
against the original Bronze snapshots during read-only replay. Original audit
success and variant uniqueness are required; competing valid content under one
observation identity is quarantined. This remains observation-only.

Added `tests/data_platform/test_native_surface_recording.py` for native
Bronze-to-Silver recording, read-only replay, exact retry, conflicting-variant
quarantine, artifact-pin integrity and original-audit enforcement. The tests are
supplied but not yet owner-QA-confirmed. Therefore surface evidence implementation
is present; native integration acceptance remains open.

This recorder does not authenticate the issuer of supplied calendar/forward/rate
artifacts, independently establish their historical availability, or claim an
atomic snapshot across Bronze and Silver databases. It does not produce paired
India VIX/surface history or establish proxy suitability. Those are separate
evidence and research gates.

The next acceptance action is operator execution of the focused surface recorder,
bundle and constant-maturity tests plus Ruff/mypy. Do not wire the surface or
India VIX candidate into VRP/DecisionLoop, publish Gold, activate live acquisition,
or change decision eligibility on the basis of this implementation alone.



## 2026-11-27 — D8 paired-source proxy study implementation

Added `src/nse_quant/research/india_vix_iv30_proxy_study.py` and focused
integration tests. The workflow replays exact retained VIX Bronze/Silver and
option-chain Bronze/surface Silver source references, derives pair availability
from successful original audit completion and recorded/receive clocks, and
rejects source pairs outside the source freshness policies or the 30-second
source-time synchronization bound.

A separate file-backed study journal stores immutable audited numerical policy
registrations, source-pinned pair sets and deterministic evaluation reports.
Policy registration must precede pair-set recording. The pair set retains the
source revision/observation pins and canonical condition-artifact bytes; the
required condition taxonomy covers all six strata: quiet, normal,
elevated-volatility, event, expiry and structural. Condition tags are supplied
from reviewed external evidence, not inferred or authenticated by this module.

The evaluator now reports aggregate and condition-specific calibration/holdout
metrics. Numerical tolerances are explicit preregistered policy inputs; no
default suitability limits have been selected. Exact pair reconstruction and
report recomputation APIs are included.

This closes the implementation gap for source-replayed pair construction and
preregistered diagnostic evaluation. It does NOT close empirical model
suitability: no real synchronized historical sample, accepted numerical policy,
or human research decision is supplied. Hashes do not authenticate external
issuers; source stores are replayed independently, not as an atomic cross-store
snapshot. All suitability/publication/decision authority flags remain false.
No VRP evaluator, DecisionLoop, Gold publication, acquisition or trading path
was changed.

Operator QA is pending. Run the focused commands recorded in
`ouput/research.md`; no local execution or passing result is claimed here.


## 2026-11-27 — Paper Loop + VRP readiness report

Added the read-only report engine
`src/nse_quant/research/paper_loop_vrp_readiness.py`, focused tests and
`scripts/paper_loop_vrp_readiness_report.py`. The paper-loop runner now writes
the latest structured decision result to
`logs/paper_loop_last_decision.json` after each cycle. The artifact includes
run ID, capture time, paper/dry-run flags and the exact result/evidence payload;
it is a latest-cycle diagnostic artifact, not an immutable run archive.

The report separately evaluates HAR-RV history, complete-session freshness,
forecast availability and walk-forward calibration; identifies the supplied IV
source and whether it is 30-day constant maturity; and reports the actual VRP
gate state. It explicitly distinguishes unavailable VRP from a measured negative
VRP, marks trailing close-to-close RV as diagnostic-only, and states that India
VIX proxy suitability is NOT evaluated by a paper-loop run. It also carries
other evidence-stage availability/completeness summaries and a bounded list of
next actions.

Run after a paper-loop cycle:

```powershell
uv run python scripts/paper_loop_vrp_readiness_report.py --input logs/paper_loop_last_decision.json
```

Optional structured output:

```powershell
uv run python scripts/paper_loop_vrp_readiness_report.py --input logs/paper_loop_last_decision.json --format json --output logs/paper_loop_vrp_readiness.json
```

This is observational diagnostics only. It does not change HAR-RV requirements,
the VRP gate, India VIX proxy acceptance, decision eligibility, publication or
trading authority. The latest-cycle JSON is overwritten by subsequent cycles;
copy/archive it externally if a run-level evidence history is required. Operator
QA is pending; no local execution or passing result is claimed.
