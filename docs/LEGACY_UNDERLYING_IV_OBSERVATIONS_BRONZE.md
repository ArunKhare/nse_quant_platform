# Legacy underlying IV observations Bronze

Audited preservation of the complete retained `main.underlying_iv_observations` base table.

## Contract

- Codec: `legacy-underlying-iv-observations-snapshot@1`
- Projection: `legacy-underlying-iv-observation@1`
- Recording: `legacy-underlying-iv-observations-bronze-recording@1`
- Command: `migrate.legacy_underlying_iv_observations@1`
- Source: `legacy_underlying_iv_observations_table_snapshot`, `origin_kind=legacy_snapshot`

## Retained source

The exact six-column source is retained: composite key `(ts, underlying, expiry)`; nullable finite binary64 `iv` and `spot`; and nullable `source`.

No natural key is invented. `ts` remains the stored composite-key aware SQL instant, not availability or execution truth. `expiry` remains a retained calendar date only. `iv` and `spot` remain retained finite binary64 values encoded exactly as hex, not IV or market truth. `source` remains a retained label, not authenticated provider identity.

## Native path

`capture_underlying_iv_observations` captures the entire exact-schema base table in one source transaction, with SQL count/text preflight, independent cell guards, and a max-plus-one row bound. `preserve_underlying_iv_observations` performs two complete captures, verifies the reviewed snapshot pin, derives and bounds every projected record before append, and writes one event/artifact/batch through the actual native Bronze store and audit ledger.

The public reader verifies the original envelope, source/session scope, complete artifact, original batch, scoped job, and exact audit history. Current legacy SQL equality remains separate from retained native replay.

This package does not recover overwritten history or original provider bytes, interpret IV or spot, prove IV validity, replay IV execution, assert availability or economic validity, publish research, or grant decision eligibility.
