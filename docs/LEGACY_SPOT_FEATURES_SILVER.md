# Legacy spot-features Silver

Persisted, source-linked Silver over the actual accepted `spot_features` Bronze reader.

- Store: `legacy-spot-features-silver-recording@1`
- Command: `normalize.legacy_spot_features@1`
- Contract: `silver.legacy_spot_feature_observations@1` `APPEND_REVISIONS`
- Source: `main.spot_features`, 15 columns, composite key `(symbol, ts)`
- Materialized: `symbol` (`VARCHAR`, required), `ts` (`TIMESTAMPTZ`, required), and 13 nullable retained finite binary64 feature values
- Per-revision composite-key uniqueness plus ordinal; no invented single natural key
- Original first-write, audit, orphan, and final-audit obligations; no healing or adoption
- Retained Silver, current native Bronze, and current legacy SQL remain distinct
- SQL scalar/record/aggregate byte preflight before transfer
- Retained feature is not feature truth, volatility truth, execution replay, or admission
- No feature interpretation or positive decision eligibility
