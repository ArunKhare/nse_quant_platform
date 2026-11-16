

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
