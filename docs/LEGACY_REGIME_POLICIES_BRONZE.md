# Legacy regime policies Bronze

Audited preservation of the complete retained `main.regime_policies` base table.

## Contract

- Codec: `legacy-regime-policies-snapshot@1`
- Projection: `legacy-regime-policy-observation@1`
- Recording: `legacy-regime-policies-bronze-recording@1`
- Command: `migrate.legacy_regime_policies@1`
- Source: `legacy_regime_policies_table_snapshot`, `origin_kind=legacy_snapshot`

## Retained source

The exact 11-column source is retained: `policy_id` sole primary key; nullable `symbol`; nullable calendar dates `train_start`, `train_end`, `test_start`, and `test_end`; opaque JSON `allowed_regimes`, `regime_metrics`, and `risk_limits`; nullable `selection_status`; and nullable aware `created_at`.

No natural key is invented. Dates remain retained calendar dates only, not availability or economic-validity evidence. `created_at` remains a nullable aware SQL instant, not availability or execution truth. `selection_status` remains a retained label, not authenticated native policy truth. JSON fields remain opaque JSON-cast text; SQL `NULL`, JSON `null` text, and empty text remain distinct.

## Native path

`capture_regime_policies` captures the entire exact-schema base table in one source transaction, with SQL count/text preflight, independent cell guards, and a max-plus-one row bound. `preserve_regime_policies` performs two complete captures, verifies the reviewed snapshot pin, derives and bounds every projected record before append, and writes one event/artifact/batch through the actual native Bronze store and audit ledger.

The public reader verifies the original envelope, source/session scope, complete artifact, original batch, scoped job, and exact audit history. Current legacy SQL equality remains separate from retained native replay.

This package does not recover overwritten history or original provider bytes, interpret regimes, metrics, or risk limits, prove policy validity, replay policy execution, assert availability or economic validity, publish research, or grant decision eligibility.
