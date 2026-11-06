# Legacy market events Silver

Persisted source-linked market-events Silver over the actual accepted Bronze reader.

## Contract

- Store: `legacy-market-events-silver-recording@1`
- Command: `normalize.legacy_market_events@1`
- Contract: `silver.legacy_market_events /1/APPEND_REVISIONS`
- Each Silver revision is bound to the exact reviewed Bronze recording fingerprint and context hash.

## Retained materialization

All fourteen source fields are materialized with exact nullability: `event_id VARCHAR NOT NULL`; nullable `event_ts`/`ingested_at TIMESTAMPTZ`; nullable `consensus_value`/`actual_value DOUBLE`; nullable `affected_underlyings`/`raw_payload VARCHAR` (declared retained JSON-cast text); nullable text fields.

No invented natural key: only per-revision `event_id` uniqueness plus ordinal. `importance` and `surprise_label` stay opaque nullable legacy labels. `affected_underlyings` and `raw_payload` stay exact nullable JSON-cast text; SQL NULL, JSON null text, and empty text remain distinct.

## Native path

`observe_market_events_bronze` reads Bronze records through the public Bronze reader and derives a bounded context. `persist_market_events_silver` requires two identical Bronze observations, then writes one Silver set, one observation per Bronze record, and one attempt, all inside one transaction with a separate audit job.

The public reader verifies the Silver context hash, recording fingerprint, and per-record coverage. Current Bronze equality remains separate from retained Silver replay.

This Silver does not interpret event importance, surprise labels, or payloads as native event truth, replay event ingestion, or grant decision eligibility.
