# Legacy positions Silver

Persisted, source-linked Silver over the actual accepted `positions` Bronze reader.

- Store: `legacy-positions-silver-recording@1`
- Command: `normalize.legacy_positions@1`
- Contract: `silver.legacy_positions_observations@1` `APPEND_REVISIONS`
- Source: `main.positions`, 22 columns, `position_id` only key
- Materialized: all 22 retained fields with exact nullability; `position_id` only key; per-revision uniqueness plus ordinal
- `expiry` remains a retained calendar DATE; `opened_at`/`closed_at` remain retained instants; prices/PnL remain retained finite binary64 values
- Per-revision `position_id` uniqueness plus ordinal; no invented natural key
- Original first-write, audit, orphan, and final-audit obligations; no healing or adoption
- Retained Silver, current native Bronze, and current legacy SQL remain distinct
- SQL scalar/record/aggregate byte preflight before transfer
- Retained position is not native position truth, broker truth, fill proof, execution replay, or admission
- No mark interpretation, PnL interpretation, or positive decision eligibility
