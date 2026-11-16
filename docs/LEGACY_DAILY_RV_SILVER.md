# Legacy daily-RV Silver (materialized)

Persisted, source-linked materialized Silver over the actual accepted `daily_rv_observations` Bronze reader.

- Store: `legacy-daily-rv-observations-silver-materialized@1`
- Command: `normalize.legacy_daily_rv_observations@1`
- Contract: `silver.legacy_daily_rv_materialized_observations@1` `APPEND_REVISIONS`
- Source: `main.daily_rv_observations`, 4 columns, composite key `(symbol, trading_date)`
- Materialized: `symbol` (`VARCHAR`), `trading_date` (`DATE`), `rv` (`DOUBLE`), `observation_count` (`BIGINT`); all non-null
- Per-revision composite-key uniqueness plus ordinal; no invented single natural key
- Original first-write, audit, orphan, and final-audit obligations; no healing or adoption
- Retained Silver, current native Bronze, and current legacy SQL remain distinct
- SQL scalar/record/aggregate byte preflight before transfer
- Retained RV is not volatility truth, execution replay, or admission
- No RV interpretation or positive decision eligibility
