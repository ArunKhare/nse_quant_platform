

## 2026-11-16 addendum: market-events Silver

Delivered (packaged, pending user QA): persisted source-linked `market_events` Silver over the actual accepted Bronze reader.

- Store: `legacy-market-events-silver-recording@1`
- Command: `normalize.legacy_market_events@1`
- Contract: `silver.legacy_market_event_observations@1` `APPEND_REVISIONS`
- Materialized: all 14 retained fields with exact nullability; `event_id` only key; per-revision uniqueness plus ordinal
- `event_ts`/`ingested_at` remain retained instants; `consensus_value`/`actual_value` remain retained finite binary64 values; JSON fields remain opaque retained text
- Original first-write, audit, orphan, and final-audit obligations; no healing or adoption
- Retained Silver, current native Bronze, and current legacy SQL remain distinct
- No payload interpretation, event replay, or positive decision eligibility

All 7 open native gates remain open. Package QA is not platform acceptance.
