# Legacy exit events Bronze

Audited preservation of the complete retained `main.exit_events` base table.

## Contract

- Codec: `legacy-exit-events-snapshot@1`
- Projection: `legacy-exit-event-observation@1`
- Recording: `legacy-exit-events-bronze-recording@1`
- Command: `migrate.legacy_exit_events@1`
- Source: `legacy_exit_events_table_snapshot`, `origin_kind=legacy_snapshot`

## Retained source

The exact eight-column source is retained: `exit_event_id` sole primary key; nullable aware `ts`; nullable `strategy_position_id`, `proposal_id`, and `strategy`; opaque JSON `triggered_reasons`; nullable `selected_reason`; and opaque JSON `details`.

No natural key is invented. `ts` remains a nullable aware SQL instant, not availability or execution truth. `selected_reason` remains a retained label, not authenticated native exit truth. `triggered_reasons` and `details` remain opaque JSON-cast text; SQL `NULL`, JSON `null` text, and empty text remain distinct.

## Native path

`capture_exit_events` captures the entire exact-schema base table in one source transaction, with SQL count/text preflight, independent cell guards, and a max-plus-one row bound. `preserve_exit_events` performs two complete captures, verifies the reviewed snapshot pin, derives and bounds every projected record before append, and writes one event/artifact/batch through the actual native Bronze store and audit ledger.

The public reader verifies the original envelope, source/session scope, complete artifact, original batch, scoped job, and exact audit history. Current legacy SQL equality remains separate from retained native replay.

This package does not recover overwritten history or original provider bytes, interpret exit reasons or details, replay exit execution, assert availability or economic validity, publish research, or grant decision eligibility.
