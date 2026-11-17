# Current native-platform status (Gate 6 addendum)

## Added

- Persisted audited decision-run coverage reconciliation Silver
  (`src/nse_quant/data_platform/audited_decision_reconciliation_silver.py`):
  immutable reconciliation of an audited native decision run and current
  Silver-backed coverage; exact replay only.

- End-to-end native iron-condor decision-run pipeline
  (`src/nse_quant/data_platform/native_iron_condor_decision_run_pipeline.py`):
  runs and records both native stages, reconciles against current coverage,
  persists the reconciliation, and exactly replays it.

- Authoritative identity and time boundary
  (`src/nse_quant/data_platform/native_authoritative_identity_time_boundary.py`):
  validates canonical underlying identity, derivative binding, and authorized
  revocation evidence.

- Reconciliation boundary integration
  (`src/nse_quant/data_platform/native_iron_condor_decision_reconciliation_boundary.py`):
  embeds and revalidates authoritative identity/time evidence in a persisted
  reconciliation.

- Native decision-loop integration
  (`src/nse_quant/data_platform/native_iron_condor_decision_loop_integration.py`):
  single read-only entry point that runs, reconciles with boundary evidence,
  persists, and replays a native decision run.

- Native decision-loop CLI
  (`src/nse_quant/data_platform/native_iron_condor_decision_loop_cli.py`):
  JSON-driven command-line entry point for the decision-loop integration.

- Native decision-loop status/query CLI
  (`src/nse_quant/data_platform/native_iron_condor_decision_loop_status_cli.py`):
  read-only inspection and exact replay of a persisted reconciliation.

- Bounded reconciliation query CLI
  (`src/nse_quant/data_platform/native_iron_condor_decision_reconciliation_query.py`):
  bounded read-only summaries of persisted reconciliations.

- Coverage evidence-link validation
  (`src/nse_quant/data_platform/native_strategy_coverage_evidence_links.py`):
  validates that every covered native requirement has a well-formed Silver
  evidence link with exact revision and recording-fingerprint pins.

- Reconciliation evidence-link integration
  (`src/nse_quant/data_platform/native_iron_condor_decision_reconciliation_evidence_links.py`):
  embeds and revalidates coverage evidence-link context in a persisted
  reconciliation.

## Unchanged

- All seven native status gates remain open.
- `authoritative_identity_and_time` remains explicitly missing and
  non-auto-coverable.
- `POINT_IN_TIME_DECISION` remains rejected.
- No eligibility grant, live trading, healing, backfill, adoption, or execution
  authority is authorized.
- Duplicate decision-run or reconciliation obligations remain rejected rather
  than healed.

## Holds

Data loading/migration held. No live acquisition, user-data migration or
backfill, real identity/key/policy/authority registration, production
publication, trading, or decision-loop cutover authorized. Package QA is not
platform acceptance.