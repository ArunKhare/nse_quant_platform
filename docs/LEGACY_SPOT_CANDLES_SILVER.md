# Legacy spot-candles Silver

Persisted, source-linked Silver over the actual accepted `spot_candles` Bronze reader.

- Store: `legacy-spot-candles-silver-recording@1`
- Command: `normalize.legacy_spot_candles@1`
- Contract: `silver.legacy_spot_candle_observations@1` `APPEND_REVISIONS`
- Source: `main.spot_candles`, 10 columns, composite key `(instrument_token, interval, ts)`
- Materialized: `instrument_token` (`BIGINT`, required), `symbol` (`VARCHAR`), `interval` (`VARCHAR`, required), `ts` (`TIMESTAMPTZ`, required), nullable `open`/`high`/`low`/`close` (`DOUBLE`), nullable `volume`/`oi` (`BIGINT`)
- Per-revision composite-key uniqueness plus ordinal; no invented single natural key
- Original first-write, audit, orphan, and final-audit obligations; no healing or adoption
- Retained Silver, current native Bronze, and current legacy SQL remain distinct
- SQL scalar/record/aggregate byte preflight before transfer
- Retained candle is not market truth, OHLCV interpretation, execution replay, or admission
- No OHLCV/volume/OI interpretation or positive decision eligibility
