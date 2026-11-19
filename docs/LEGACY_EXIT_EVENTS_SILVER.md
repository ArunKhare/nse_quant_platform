# Legacy exit events Silver

Persisted source-linked exit-events Silver over the actual accepted Bronze reader.

## Contract

- Store: `legacy-exit-events-silver-recording@1`
- Command: `normalize.legacy_exit_events@1`
- Contract: `silver.legacy_exit_events /1/APPEND_REVISIONS`
- Each Silver revision is bound to the exact reviewed Bronze recording fingerprint and context hash.

## Retained materialization

All eight source fields are materialized with exact nullability: `exit_event_id VARCHAR NOT NULL`; nullable `ts TIMESTAMPTZ`; nullable `strategy_position_id`, `proposal_id`, `strategy`, `selected_reason`, `triggered_reasons`, and `details VARCHAR` (declared retained JSON-cast text).

No invented natural key: only per-revision `exit_event_id` uniqueness plus ordinal. `selected_reason` stays an opaque nullable legacy label, not native exit truth. `triggered_reasons` and `details` stay exact nullable JSON-cast text; SQL NULL, JSON null text, and empty text remain distinct.

## Native path

`observe_exit_events_bronze` reads Bronze records through the public Bronze reader and derives a bounded context. `persist_exit_events_silver` requires two identical Bronze observations, then writes one Silver set, one observation per Bronze record, and one attempt, all inside one transaction with a separate audit job.

The public reader verifies the Silver context hash, recording fingerprint, and per-record coverage. Current Bronze equality remains separate from retained Silver replay.

This Silver does not interpret triggered reasons or details, replay exit execution, or grant decision eligibility.
