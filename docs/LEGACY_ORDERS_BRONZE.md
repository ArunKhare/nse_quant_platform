# Legacy orders Bronze

Audited preservation of the complete retained `main.orders` base table.

## Contract

- Codec: `legacy-orders-snapshot@1`
- Projection: `legacy-order-observation@1`
- Recording: `legacy-orders-bronze-recording@1`
- Command: `migrate.legacy_orders@1`
- Source: `legacy_orders_table_snapshot`, `origin_kind=legacy_snapshot`

## Retained source

The exact twelve-column source is:

- `order_id VARCHAR PRIMARY KEY`
- `ts TIMESTAMPTZ`
- `run_id VARCHAR`
- `proposal_id VARCHAR`
- `strategy VARCHAR`
- `broker VARCHAR`
- `status VARCHAR`
- `limit_price DOUBLE`
- `filled_price DOUBLE`
- `filled_at TIMESTAMPTZ`
- `reject_reason VARCHAR`
- `payload JSON`

Only `order_id` is the retained key. All other fields remain nullable, and no natural key is invented across run, proposal, strategy, broker, status, or time.

`ts` and `filled_at` remain nullable aware SQL instants; they are not availability or execution truth. `limit_price` and `filled_price` are retained finite binary64 values encoded exactly as hex. `broker` and `status` are retained labels, not authenticated broker identity or execution truth. `payload` remains exact nullable `CAST(JSON AS VARCHAR)` text; SQL `NULL`, JSON `null` text, and empty text remain distinct.

A `filled_price` without `filled_at` is retained as an observation flag; it is not repaired, inferred, or treated as a fill proof.

## Native path

`capture_orders` captures the entire exact-schema base table in one source transaction, with SQL count/text preflight, independent cell guards, and a max-plus-one row bound. `preserve_orders` performs two complete captures, verifies the reviewed snapshot pin, derives and bounds every projected record before append, and writes one event/artifact/batch through the actual native Bronze store and audit ledger.

The public reader verifies the original envelope, source/session scope, complete artifact, original batch, scoped job, and exact audit history. Current legacy SQL equality remains separate from retained native replay.

This package does not recover overwritten history or original provider bytes, authenticate a broker, prove fills, replay order execution, assert availability or economic validity, publish research, or grant decision eligibility.
