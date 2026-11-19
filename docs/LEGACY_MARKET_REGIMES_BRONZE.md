# Legacy market regimes Bronze

Audited preservation of the complete retained `main.market_regimes` base table.

## Contract

- Codec: `legacy-market-regimes-snapshot@1`
- Projection: `legacy-market-regime-observation@1`
- Recording: `legacy-market-regimes-bronze-recording@1`
- Command: `migrate.legacy_market_regimes@1`
- Source: `legacy_market_regimes_table_snapshot`, `origin_kind=legacy_snapshot`

## Retained source

The exact seven-column source is retained: composite key `(symbol, ts)`; nullable `trend_regime`, `volatility_regime`, `iv_regime`, and `regime`; and opaque JSON `features`.

No natural key is invented. `ts` remains the stored composite-key aware SQL instant, not availability or execution truth. All regime fields remain retained labels, not authenticated native regime truth. `features` remains opaque JSON-cast text; SQL `NULL`, JSON `null` text, and empty text remain distinct.

## Native path

`capture_market_regimes` captures the entire exact-schema base table in one source transaction, with SQL count/text preflight, independent cell guards, and a max-plus-one row bound. `preserve_market_regimes` performs two complete captures, verifies the reviewed snapshot pin, derives and bounds every projected record before append, and writes one event/artifact/batch through the actual native Bronze store and audit ledger.

The public reader verifies the original envelope, source/session scope, complete artifact, original batch, scoped job, and exact audit history. Current legacy SQL equality remains separate from retained native replay.

This package does not recover overwritten history or original provider bytes, interpret regimes or features, prove regime validity, replay regime execution, assert availability or economic validity, publish research, or grant decision eligibility.
