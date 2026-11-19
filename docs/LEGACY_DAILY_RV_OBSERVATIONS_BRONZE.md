# Legacy daily RV observations Bronze

Audited preservation of the complete retained `main.daily_rv_observations` base table.

## Contract

- Codec: `legacy-daily-rv-observations-snapshot@1`
- Projection: `legacy-daily-rv-observation@1`
- Recording: `legacy-daily-rv-observations-bronze-recording@1`
- Command: `migrate.legacy_daily_rv_observations@1`
- Source: `legacy_daily_rv_observations_table_snapshot`, `origin_kind=legacy_snapshot`

## Retained source

The exact four-column source is retained: composite key `(symbol, trading_date)`; non-null finite binary64 `rv`; and non-null `observation_count BIGINT`.

No natural key is invented. `trading_date` remains a retained calendar date only, not availability or economic-validity evidence. `rv` remains a retained finite binary64 value encoded exactly as hex, not volatility truth. `observation_count` remains a retained SQL integer, not interpreted sampling evidence.

## Native path

`capture_daily_rv_observations` captures the entire exact-schema base table in one source transaction, with SQL count/text preflight, independent cell guards, and a max-plus-one row bound. `preserve_daily_rv_observations` performs two complete captures, verifies the reviewed snapshot pin, derives and bounds every projected record before append, and writes one event/artifact/batch through the actual native Bronze store and audit ledger.

The public reader verifies the original envelope, source/session scope, complete artifact, original batch, scoped job, and exact audit history. Current legacy SQL equality remains separate from retained native replay.

This package does not recover overwritten history or original provider bytes, interpret RV or observation counts, prove volatility validity, replay RV execution, assert availability or economic validity, publish research, or grant decision eligibility.
