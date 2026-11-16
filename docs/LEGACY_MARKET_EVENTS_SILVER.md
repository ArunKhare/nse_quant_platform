# Legacy market-events Silver

Persisted, source-linked Silver over the actual accepted `market_events` Bronze reader.

- Store: `legacy-market-events-silver-recording@1`
- Command: `normalize.legacy_market_events@1`
- Contract: `silver.legacy_market_event_observations@1` `APPEND_REVISIONS`
- Source: `main.market_events`, 14 columns, `event_id` only key
- Materialized: `event_id`, nullable `source`/`event_type`/`title`/`description`/`symbol`/`importance`/`surprise_label`, nullable `event_ts`/`ingested_at` (`TIMESTAMPTZ`), nullable `consensus_value`/`actual_value` (`DOUBLE`), nullable opaque `affected_underlyings`/`raw_payload` (`VARCHAR` from retained JSON-cast text)
- Per-revision `event_id` uniqueness plus ordinal; no invented natural key
- Original first-write, audit, orphan, and final-audit obligations; no healing or adoption
- Retained Silver, current native Bronze, and current legacy SQL remain distinct
- SQL scalar/record/aggregate byte preflight before transfer
- Retained event is not event truth, event replay, or admission
- No payload interpretation or positive decision eligibility
