# Legacy spot candles Bronze

Audited preservation of the complete retained `main.spot_candles` base table.

## Contract

- Codec: `legacy-spot-candles-snapshot@1`
- Projection: `legacy-spot-candle-observation@1`
- Recording: `legacy-spot-candles-bronze-recording@1`
- Command: `migrate.legacy_spot_candles@1`
- Source: `legacy_spot_candles_table_snapshot`, `origin_kind=legacy_snapshot`

## Retained source

The exact ten-column source is retained: composite key `(instrument_token, interval, ts)`; nullable `symbol`; finite binary64 `open`, `high`, `low`, and `close`; nullable `volume BIGINT`; and nullable `oi BIGINT`.

No natural key is invented. `ts` remains the stored composite-key aware SQL instant, not availability or execution truth. OHLCV values remain retained finite binary64 values encoded exactly as hex, not market truth or economic-validity evidence. `volume` and `oi` remain nullable SQL integers, not interpreted market activity.

## Native path

`capture_spot_candles` captures the entire exact-schema base table in one source transaction, with SQL count/text preflight, independent cell guards, and a max-plus-one row bound. `preserve_spot_candles` performs two complete captures, verifies the reviewed snapshot pin, derives and bounds every projected record before append, and writes one event/artifact/batch through the actual native Bronze store and audit ledger.

The public reader verifies the original envelope, source/session scope, complete artifact, original batch, scoped job, and exact audit history. Current legacy SQL equality remains separate from retained native replay.

This package does not recover overwritten history or original provider bytes, interpret OHLCV, volume, or open interest, prove market truth, replay candle execution, assert availability or economic validity, publish research, or grant decision eligibility.
