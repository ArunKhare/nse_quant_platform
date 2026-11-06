# Legacy orders Silver

Persisted source-linked orders Silver over the actual accepted Bronze reader.

## Contract

- Store: `legacy-orders-silver-recording@1`
- Command: `normalize.legacy_orders@1`
- Contract: `silver.legacy_orders /1/APPEND_REVISIONS`
- Each Silver revision is bound to the exact reviewed Bronze recording fingerprint and context hash.

## Retained materialization

All twelve source fields are materialized with exact nullability: `order_id VARCHAR NOT NULL`; nullable `ts`/`filled_at TIMESTAMPTZ`; nullable `run_id`, `proposal_id`, `strategy`, `broker`, `status`, `reject_reason`, and `payload VARCHAR` (declared retained JSON-cast text); nullable `limit_price`/`filled_price DOUBLE`.

No invented natural key: only per-revision `order_id` uniqueness plus ordinal. `status` stays a retained legacy label, not broker or execution truth. `payload` stays exact nullable JSON-cast text; SQL NULL, JSON null text, and empty text remain distinct.

## Native path

`observe_orders_bronze` reads Bronze records through the public Bronze reader and derives a bounded context. `persist_orders_silver` requires two identical Bronze observations, then writes one Silver set, one observation per Bronze record, and one attempt, all inside one transaction with a separate audit job.

The public reader verifies the Silver context hash, recording fingerprint, and per-record coverage. Current Bronze equality remains separate from retained Silver replay.

This Silver does not authenticate broker identity, verify fill evidence, interpret status or payload, replay order execution, or grant decision eligibility.
