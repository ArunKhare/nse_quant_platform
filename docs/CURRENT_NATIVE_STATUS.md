# Current native-platform status

Status reconciliation: 2026-11-15. This document separates source inspection,
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
- This documentation delivery: text/patch/archive checks only; no repository
  execution, native integration, pytest, Ruff, mypy, uv or local Git verification.


## 2026-11-16 addendum: risk-decisions Silver

Delivered (packaged, pending user QA): persisted source-linked `risk_decisions` Silver over the actual accepted Bronze reader.

- Store: `legacy-risk-decisions-silver-recording@1`
- Command: `normalize.legacy_risk_decisions@1`
- Contract: `silver.legacy_risk_decisions_observations@1` `APPEND_REVISIONS`
- Materialized: all 8 retained fields with exact nullability; `risk_decision_id` only key; per-revision uniqueness plus ordinal
- `approved` remains a nullable retained legacy claim, never native risk approval
- `reasons`/`checks` remain opaque retained JSON-cast text; SQL NULL distinct from JSON null
- Original first-write, audit, orphan, and final-audit obligations; no healing or adoption
- Retained Silver, current native Bronze, and current legacy SQL remain distinct
- No payload interpretation, admission, original risk replay, or positive decision eligibility

All 7 open native gates remain open. Package QA is not platform acceptance.


## 2026-11-16 addendum: risk-decisions Silver

Delivered (packaged, pending user QA): persisted source-linked `risk_decisions` Silver over the actual accepted Bronze reader.

- Store: `legacy-risk-decisions-silver-recording@1`
- Command: `normalize.legacy_risk_decisions@1`
- Contract: `silver.legacy_risk_decisions_observations@1` `APPEND_REVISIONS`
- Materialized: all 8 retained fields with exact nullability; `risk_decision_id` only key; per-revision uniqueness plus ordinal
- `approved` remains a nullable retained legacy claim, never native risk approval
- `reasons`/`checks` remain opaque retained JSON-cast text; SQL NULL distinct from JSON null
- Original first-write, audit, orphan, and final-audit obligations; no healing or adoption
- Retained Silver, current native Bronze, and current legacy SQL remain distinct
- No payload interpretation, admission, original risk replay, or positive decision eligibility

All 7 open native gates remain open. Package QA is not platform acceptance.


## 2026-11-16 addendum: risk-decisions Silver

Delivered (packaged, pending user QA): persisted source-linked `risk_decisions` Silver over the actual accepted Bronze reader.

- Store: `legacy-risk-decisions-silver-recording@1`
- Command: `normalize.legacy_risk_decisions@1`
- Contract: `silver.legacy_risk_decisions_observations@1` `APPEND_REVISIONS`
- Materialized: all 8 retained fields with exact nullability; `risk_decision_id` only key; per-revision uniqueness plus ordinal
- `approved` remains a nullable retained legacy claim, never native risk approval
- `reasons`/`checks` remain opaque retained JSON-cast text; SQL NULL distinct from JSON null
- Original first-write, audit, orphan, and final-audit obligations; no healing or adoption
- Retained Silver, current native Bronze, and current legacy SQL remain distinct
- No payload interpretation, admission, original risk replay, or positive decision eligibility

All 7 open native gates remain open. Package QA is not platform acceptance.


## 2026-11-16 addendum: risk-decisions Silver

Delivered (packaged, pending user QA): persisted source-linked `risk_decisions` Silver over the actual accepted Bronze reader.

- Store: `legacy-risk-decisions-silver-recording@1`
- Command: `normalize.legacy_risk_decisions@1`
- Contract: `silver.legacy_risk_decisions_observations@1` `APPEND_REVISIONS`
- Materialized: all 8 retained fields with exact nullability; `risk_decision_id` only key; per-revision uniqueness plus ordinal
- `approved` remains a nullable retained legacy claim, never native risk approval
- `reasons`/`checks` remain opaque retained JSON-cast text; SQL NULL distinct from JSON null
- Original first-write, audit, orphan, and final-audit obligations; no healing or adoption
- Retained Silver, current native Bronze, and current legacy SQL remain distinct
- No payload interpretation, admission, original risk replay, or positive decision eligibility

All 7 open native gates remain open. Package QA is not platform acceptance.


## 2026-11-16 addendum: risk-decisions Silver

Delivered (packaged, pending user QA): persisted source-linked `risk_decisions` Silver over the actual accepted Bronze reader.

- Store: `legacy-risk-decisions-silver-recording@1`
- Command: `normalize.legacy_risk_decisions@1`
- Contract: `silver.legacy_risk_decisions_observations@1` `APPEND_REVISIONS`
- Materialized: all 8 retained fields with exact nullability; `risk_decision_id` only key; per-revision uniqueness plus ordinal
- `approved` remains a nullable retained legacy claim, never native risk approval
- `reasons`/`checks` remain opaque retained JSON-cast text; SQL NULL distinct from JSON null
- Original first-write, audit, orphan, and final-audit obligations; no healing or adoption
- Retained Silver, current native Bronze, and current legacy SQL remain distinct
- No payload interpretation, admission, original risk replay, or positive decision eligibility

All 7 open native gates remain open. Package QA is not platform acceptance.


## 2026-11-16 addendum: decisions Silver

Delivered (packaged, pending user QA): persisted source-linked `decisions` Silver over the actual accepted Bronze reader.

- Store: `legacy-decisions-silver-recording@1`
- Command: `normalize.legacy_decisions@1`
- Contract: `silver.legacy_decisions_observations@1` `APPEND_REVISIONS`
- Materialized: all 9 retained fields with exact nullability; `decision_id` only key; per-revision uniqueness plus ordinal
- `expiry` remains a retained calendar DATE; `payload` remains opaque retained JSON-cast text
- Original first-write, audit, orphan, and final-audit obligations; no healing or adoption
- Retained Silver, current native Bronze, and current legacy SQL remain distinct
- No payload interpretation, admission, original decision replay, or positive decision eligibility

All 7 open native gates remain open. Package QA is not platform acceptance.


## 2026-11-16 addendum: decisions Silver

Delivered (packaged, pending user QA): persisted source-linked `decisions` Silver over the actual accepted Bronze reader.

- Store: `legacy-decisions-silver-recording@1`
- Command: `normalize.legacy_decisions@1`
- Contract: `silver.legacy_decisions_observations@1` `APPEND_REVISIONS`
- Materialized: all 9 retained fields with exact nullability; `decision_id` only key; per-revision uniqueness plus ordinal
- `expiry` remains a retained calendar DATE; `payload` remains opaque retained JSON-cast text
- Original first-write, audit, orphan, and final-audit obligations; no healing or adoption
- Retained Silver, current native Bronze, and current legacy SQL remain distinct
- No payload interpretation, admission, original decision replay, or positive decision eligibility

All 7 open native gates remain open. Package QA is not platform acceptance.


## 2026-11-16 addendum: orders Silver

Delivered (packaged, pending user QA): persisted source-linked `orders` Silver over the actual accepted Bronze reader.

- Store: `legacy-orders-silver-recording@1`
- Command: `normalize.legacy_orders@1`
- Contract: `silver.legacy_orders_observations@1` `APPEND_REVISIONS`
- Materialized: all 12 retained fields with exact nullability; `order_id` only key; per-revision uniqueness plus ordinal
- `limit_price`/`filled_price` remain retained finite binary64 values; `payload` remains opaque retained JSON-cast text
- Original first-write, audit, orphan, and final-audit obligations; no healing or adoption
- Retained Silver, current native Bronze, and current legacy SQL remain distinct
- No payload interpretation, execution replay, or positive decision eligibility

All 7 open native gates remain open. Package QA is not platform acceptance.


## 2026-11-16 addendum: positions Silver

Delivered (packaged, pending user QA): persisted source-linked `positions` Silver over the actual accepted Bronze reader.

- Store: `legacy-positions-silver-recording@1`
- Command: `normalize.legacy_positions@1`
- Contract: `silver.legacy_positions_observations@1` `APPEND_REVISIONS`
- Materialized: all 22 retained fields with exact nullability; `position_id` only key; per-revision uniqueness plus ordinal
- `expiry` remains a retained calendar DATE; `opened_at`/`closed_at` remain retained instants; prices/PnL remain retained finite binary64 values
- Original first-write, audit, orphan, and final-audit obligations; no healing or adoption
- Retained Silver, current native Bronze, and current legacy SQL remain distinct
- No mark interpretation, PnL interpretation, execution replay, or positive decision eligibility

All 7 open native gates remain open. Package QA is not platform acceptance.


## 2026-11-16 addendum: positions Silver

Delivered (packaged, pending user QA): persisted source-linked `positions` Silver over the actual accepted Bronze reader.

- Store: `legacy-positions-silver-recording@1`
- Command: `normalize.legacy_positions@1`
- Contract: `silver.legacy_positions_observations@1` `APPEND_REVISIONS`
- Materialized: all 22 retained fields with exact nullability; `position_id` only key; per-revision uniqueness plus ordinal
- `expiry` remains a retained calendar DATE; `opened_at`/`closed_at` remain retained instants; prices/PnL remain retained finite binary64 values
- Original first-write, audit, orphan, and final-audit obligations; no healing or adoption
- Retained Silver, current native Bronze, and current legacy SQL remain distinct
- No mark interpretation, PnL interpretation, execution replay, or positive decision eligibility

All 7 open native gates remain open. Package QA is not platform acceptance.


## 2026-11-16 addendum: spot-features Silver

Delivered (packaged, pending user QA): persisted source-linked `spot_features` Silver over the actual accepted Bronze reader.

- Store: `legacy-spot-features-silver-recording@1`
- Command: `normalize.legacy_spot_features@1`
- Contract: `silver.legacy_spot_feature_observations@1` `APPEND_REVISIONS`
- Materialized: `symbol` + `ts` composite key, plus 13 nullable retained finite binary64 feature values
- Per-revision composite-key uniqueness plus ordinal; no invented single natural key
- Original first-write, audit, orphan, and final-audit obligations; no healing or adoption
- Retained Silver, current native Bronze, and current legacy SQL remain distinct
- No feature interpretation, execution replay, or positive decision eligibility

All 7 open native gates remain open. Package QA is not platform acceptance.


## 2026-11-16 addendum: daily-RV Silver (materialized)

Delivered (packaged, pending user QA): persisted source-linked materialized `daily_rv_observations` Silver over the actual accepted Bronze reader.

- Store: `legacy-daily-rv-observations-silver-materialized@1`
- Command: `normalize.legacy_daily_rv_observations@1`
- Contract: `silver.legacy_daily_rv_materialized_observations@1` `APPEND_REVISIONS`
- Materialized: `symbol` + `trading_date` composite key, plus non-null `rv` and `observation_count`
- Per-revision composite-key uniqueness plus ordinal; no invented single natural key
- Original first-write, audit, orphan, and final-audit obligations; no healing or adoption
- Retained Silver, current native Bronze, and current legacy SQL remain distinct
- No RV interpretation, execution replay, or positive decision eligibility

All 7 open native gates remain open. Package QA is not platform acceptance.


## 2026-11-16 addendum: daily-RV Silver (materialized)

Delivered (packaged, pending user QA): persisted source-linked materialized `daily_rv_observations` Silver over the actual accepted Bronze reader.

- Store: `legacy-daily-rv-observations-silver-materialized@1`
- Command: `normalize.legacy_daily_rv_observations@1`
- Contract: `silver.legacy_daily_rv_materialized_observations@1` `APPEND_REVISIONS`
- Materialized: `symbol` + `trading_date` composite key, plus non-null `rv` and `observation_count`
- Per-revision composite-key uniqueness plus ordinal; no invented single natural key
- Original first-write, audit, orphan, and final-audit obligations; no healing or adoption
- Retained Silver, current native Bronze, and current legacy SQL remain distinct
- No RV interpretation, execution replay, or positive decision eligibility

All 7 open native gates remain open. Package QA is not platform acceptance.


## 2026-11-16 addendum: daily-RV Silver (materialized)

Delivered (packaged, pending user QA): persisted source-linked materialized `daily_rv_observations` Silver over the actual accepted Bronze reader.

- Store: `legacy-daily-rv-observations-silver-materialized@1`
- Command: `normalize.legacy_daily_rv_observations@1`
- Contract: `silver.legacy_daily_rv_materialized_observations@1` `APPEND_REVISIONS`
- Materialized: `symbol` + `trading_date` composite key, plus non-null `rv` and `observation_count`
- Per-revision composite-key uniqueness plus ordinal; no invented single natural key
- Original first-write, audit, orphan, and final-audit obligations; no healing or adoption
- Retained Silver, current native Bronze, and current legacy SQL remain distinct
- No RV interpretation, execution replay, or positive decision eligibility

All 7 open native gates remain open. Package QA is not platform acceptance.


## 2026-11-16 addendum: daily-RV Silver (materialized)

Delivered (packaged, pending user QA): persisted source-linked materialized `daily_rv_observations` Silver over the actual accepted Bronze reader.

- Store: `legacy-daily-rv-observations-silver-materialized@1`
- Command: `normalize.legacy_daily_rv_observations@1`
- Contract: `silver.legacy_daily_rv_materialized_observations@1` `APPEND_REVISIONS`
- Materialized: `symbol` + `trading_date` composite key, plus non-null `rv` and `observation_count`
- Per-revision composite-key uniqueness plus ordinal; no invented single natural key
- Original first-write, audit, orphan, and final-audit obligations; no healing or adoption
- Retained Silver, current native Bronze, and current legacy SQL remain distinct
- No RV interpretation, execution replay, or positive decision eligibility

All 7 open native gates remain open. Package QA is not platform acceptance.


## 2026-11-16 addendum: daily-RV Silver (materialized)

Delivered (packaged, pending user QA): persisted source-linked materialized `daily_rv_observations` Silver over the actual accepted Bronze reader.

- Store: `legacy-daily-rv-observations-silver-materialized@1`
- Command: `normalize.legacy_daily_rv_observations@1`
- Contract: `silver.legacy_daily_rv_materialized_observations@1` `APPEND_REVISIONS`
- Materialized: `symbol` + `trading_date` composite key, plus non-null `rv` and `observation_count`
- Per-revision composite-key uniqueness plus ordinal; no invented single natural key
- Original first-write, audit, orphan, and final-audit obligations; no healing or adoption
- Retained Silver, current native Bronze, and current legacy SQL remain distinct
- No RV interpretation, execution replay, or positive decision eligibility

All 7 open native gates remain open. Package QA is not platform acceptance.


## 2026-11-16 addendum: decision-evidence Silver (materialized)

Delivered (packaged, pending user QA): persisted source-linked materialized `decision_evidence` Silver over the actual accepted Bronze reader.

- Store: `legacy-decision-evidence-silver-materialized@1`
- Command: `normalize.legacy_decision_evidence@1`
- Contract: `silver.legacy_decision_evidence_materialized_observations@1` `APPEND_REVISIONS`
- Materialized: `evidence_id`, `run_id`, wall-clock `ts` (`TIMESTAMP`), `symbol`, `plugin`, nullable `available`, nullable opaque `payload_json`
- Natural key `(run_id, ts, symbol, plugin)`; per-revision uniqueness plus ordinal
- Original first-write, audit, orphan, and final-audit obligations; no healing or adoption
- Retained Silver, current native Bronze, and current legacy SQL remain distinct
- No payload interpretation, timezone inference, or positive decision eligibility

All 7 open native gates remain open. Package QA is not platform acceptance.


## 2026-11-16 addendum: decision-evidence Silver (materialized)

Delivered (packaged, pending user QA): persisted source-linked materialized `decision_evidence` Silver over the actual accepted Bronze reader.

- Store: `legacy-decision-evidence-silver-materialized@1`
- Command: `normalize.legacy_decision_evidence@1`
- Contract: `silver.legacy_decision_evidence_materialized_observations@1` `APPEND_REVISIONS`
- Materialized: `evidence_id`, `run_id`, wall-clock `ts` (`TIMESTAMP`), `symbol`, `plugin`, nullable `available`, nullable opaque `payload_json`
- Natural key `(run_id, ts, symbol, plugin)`; per-revision uniqueness plus ordinal
- Original first-write, audit, orphan, and final-audit obligations; no healing or adoption
- Retained Silver, current native Bronze, and current legacy SQL remain distinct
- No payload interpretation, timezone inference, or positive decision eligibility

All 7 open native gates remain open. Package QA is not platform acceptance.


## 2026-11-16 addendum: decision-evidence Silver (materialized)

Delivered (packaged, pending user QA): persisted source-linked materialized `decision_evidence` Silver over the actual accepted Bronze reader.

- Store: `legacy-decision-evidence-silver-materialized@1`
- Command: `normalize.legacy_decision_evidence@1`
- Contract: `silver.legacy_decision_evidence_materialized_observations@1` `APPEND_REVISIONS`
- Materialized: `evidence_id`, `run_id`, wall-clock `ts` (`TIMESTAMP`), `symbol`, `plugin`, nullable `available`, nullable opaque `payload_json`
- Natural key `(run_id, ts, symbol, plugin)`; per-revision uniqueness plus ordinal
- Original first-write, audit, orphan, and final-audit obligations; no healing or adoption
- Retained Silver, current native Bronze, and current legacy SQL remain distinct
- No payload interpretation, timezone inference, or positive decision eligibility

All 7 open native gates remain open. Package QA is not platform acceptance.


## 2026-11-16 addendum: decision-evidence Silver (materialized)

Delivered (packaged, pending user QA): persisted source-linked materialized `decision_evidence` Silver over the actual accepted Bronze reader.

- Store: `legacy-decision-evidence-silver-materialized@1`
- Command: `normalize.legacy_decision_evidence@1`
- Contract: `silver.legacy_decision_evidence_materialized_observations@1` `APPEND_REVISIONS`
- Materialized: `evidence_id`, `run_id`, wall-clock `ts` (`TIMESTAMP`), `symbol`, `plugin`, nullable `available`, nullable opaque `payload_json`
- Natural key `(run_id, ts, symbol, plugin)`; per-revision uniqueness plus ordinal
- Original first-write, audit, orphan, and final-audit obligations; no healing or adoption
- Retained Silver, current native Bronze, and current legacy SQL remain distinct
- No payload interpretation, timezone inference, or positive decision eligibility

All 7 open native gates remain open. Package QA is not platform acceptance.


## 2026-11-16 addendum: market-events Silver

Delivered (packaged, pending user QA): persisted source-linked `market_events` Silver over the actual accepted Bronze reader.

- Store: `legacy-market-events-silver-recording@1`
- Command: `normalize.legacy_market_events@1`
- Contract: `silver.legacy_market_event_observations@1` `APPEND_REVISIONS`
- Materialized: all 14 retained fields with exact nullability; `event_id` only key; per-revision uniqueness plus ordinal
- `event_ts`/`ingested_at` remain retained instants; `consensus_value`/`actual_value` remain retained finite binary64 values; JSON fields remain opaque retained text
- Original first-write, audit, orphan, and final-audit obligations; no healing or adoption
- Retained Silver, current native Bronze, and current legacy SQL remain distinct
- No payload interpretation, event replay, or positive decision eligibility

All 7 open native gates remain open. Package QA is not platform acceptance.


## 2026-11-16 addendum: spot-candles Silver

Delivered (packaged, pending user QA): persisted source-linked `spot_candles` Silver over the actual accepted Bronze reader.

- Store: `legacy-spot-candles-silver-recording@1`
- Command: `normalize.legacy_spot_candles@1`
- Contract: `silver.legacy_spot_candle_observations@1` `APPEND_REVISIONS`
- Materialized: `instrument_token` + `interval` + `ts` composite key, plus `symbol` and nullable OHLC/Volume/OI retained values
- Per-revision composite-key uniqueness plus ordinal; no invented single natural key
- Original first-write, audit, orphan, and final-audit obligations; no healing or adoption
- Retained Silver, current native Bronze, and current legacy SQL remain distinct
- No OHLCV interpretation, execution replay, or positive decision eligibility

All 7 open native gates remain open. Package QA is not platform acceptance.


## 2026-11-16 addendum: regime-policies Silver

Delivered (packaged, pending user QA): persisted source-linked `regime_policies` Silver over the plural whole-table Bronze reader.

- Store: `legacy-regime-policies-silver-recording@1`
- Command: `persist.legacy_regime_policies_silver@1`
- Source reader: `read_regime_policies_bronze` (plural, no layout pin)
- Retained: exact reviewed record bytes plus context and ordinal coverage
- Original first-write, audit, orphan, and final-audit obligations; no healing or adoption
- Retained policy Silver is not policy truth, authorization, or execution replay

All 7 open native gates remain open. Package QA is not platform acceptance.


## 2026-11-16 addendum: regime-policies Silver

Delivered (packaged, pending user QA): persisted source-linked `regime_policies` Silver over the plural whole-table Bronze reader.

- Store: `legacy-regime-policies-silver-recording@1`
- Command: `persist.legacy_regime_policies_silver@1`
- Source reader: `read_regime_policies_bronze` (plural, no layout pin)
- Retained: exact reviewed record bytes plus context and ordinal coverage
- Original first-write, audit, orphan, and final-audit obligations; no healing or adoption
- Retained policy Silver is not policy truth, authorization, or execution replay

All 7 open native gates remain open. Package QA is not platform acceptance.


## 2026-11-17 addendum: native strategy input coverage

Delivered (packaged, pending user QA): source-reconciled input-coverage reconciliation for `iron_condor_monitor`.

- Module: `native_strategy_input_coverage.py`
- Inventory: `native_strategy_requirements.REQUIREMENTS`
- Statuses: `covered`, `missing`, `unlinked`
- `authoritative_identity_and_time` is never auto-coverable
- No healing, backfill, eligibility grant, or execution authority
- `decision_eligibility_asserted=False` always

All 7 open native gates remain open. Package QA is not platform acceptance.


## 2026-11-17 addendum: evidence-linked native strategy input coverage

Delivered (packaged, pending user QA): evidence-linked input-coverage derivation for `iron_condor_monitor`.

- Module: `native_strategy_input_coverage_evidence.py`
- Evidence pin: `requirement_id`, 64-hex `revision_id`, 64-hex `recording_fingerprint`, positive `row_count`
- Statuses: `covered` only with a valid pin; otherwise `missing`
- `authoritative_identity_and_time` is never auto-coverable
- No healing, backfill, eligibility grant, or execution authority
- `decision_eligibility_asserted=False` always

All 7 open native gates remain open. Package QA is not platform acceptance.


## 2026-11-17 addendum: Silver-backed native strategy input coverage

Delivered (packaged, pending user QA): Silver-backed input-coverage derivation for `iron_condor_monitor`.

- Module: `native_strategy_input_coverage_silver.py`
- Mapped requirements: `iv_rank_and_history`, `iv_rv_spread`, `expected_move`, `effective_proposal_configuration`, `market_session`
- Unmapped requirements remain explicitly `missing`; never invented or healed
- Evidence pins come from actual Silver recording metadata (revision id, fingerprint, row count)
- No eligibility, execution authority, or backfill
- `decision_eligibility_asserted=False` always

All 7 open native gates remain open. Package QA is not platform acceptance.


## 2026-11-17 addendum: native option-chain snapshot

Delivered (packaged, pending user QA): native option-chain snapshot Bronze and Silver, plus Silver-backed coverage mapping for `chain_time_expiry_spot`, `option_chain_and_contract_terms`, and `candidate_liquidity`.

- Codec: `native-option-chain-snapshot@1`
- Bronze: `native-option-chain-snapshot-bronze-recording@1`
- Silver: `native-option-chain-snapshot-silver-recording@1`
- Retained: exact reviewed snapshot artifact and per-quote records
- Original first-write, audit, orphan, and final-audit obligations; no healing or adoption
- Retained snapshot is not market truth, option pricing truth, or execution replay
- `authoritative_identity_and_time` remains explicitly unmapped and never auto-coverable
- No positive decision eligibility

All 7 open native gates remain open. Package QA is not platform acceptance.
