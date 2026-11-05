# Legacy spot features Bronze

Audited preservation of the complete retained `main.spot_features` base table.

## Contract

- Codec: `legacy-spot-features-snapshot@1`
- Projection: `legacy-spot-feature-observation@1`
- Recording: `legacy-spot-features-bronze-recording@1`
- Command: `migrate.legacy_spot_features@1`
- Source: `legacy_spot_features_table_snapshot`, `origin_kind=legacy_snapshot`

## Retained source

The exact 15-column source is retained: composite key `(symbol, ts)`; finite binary64 `close` and 12 nullable feature values.

No natural key is invented. `ts` remains the stored composite-key aware SQL instant, not availability or execution truth. Every feature remains a retained finite binary64 value encoded exactly as hex, not feature truth or economic-validity evidence.

## Native path

`capture_spot_features` captures the entire exact-schema base table in one source transaction, with SQL count/text preflight, independent cell guards, and a max-plus-one row bound. `preserve_spot_features` performs two complete captures, verifies the reviewed snapshot pin, derives and bounds every projected record before append, and writes one event/artifact/batch through the actual native Bronze store and audit ledger.

The public reader verifies the original envelope, source/session scope, complete artifact, original batch, scoped job, and exact audit history. Current legacy SQL equality remains separate from retained native replay.

This package does not recover overwritten history or original provider bytes, interpret features, trends, or volatility, prove feature validity, replay feature execution, assert availability or economic validity, publish research, or grant decision eligibility.
