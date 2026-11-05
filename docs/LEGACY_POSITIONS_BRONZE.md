# Legacy positions Bronze

Audited preservation of the complete retained `main.positions` base table.

## Contract

- Codec: `legacy-positions-snapshot@1`
- Projection: `legacy-position-observation@1`
- Recording: `legacy-positions-bronze-recording@1`
- Command: `migrate.legacy_positions@1`
- Source: `legacy_positions_table_snapshot`, `origin_kind=legacy_snapshot`

## Retained source

The exact 22-column source is retained, including `position_id` as the sole primary key, nullable strategy/proposal/instrument fields, finite binary64 prices and P&L, nullable aware `opened_at` / `closed_at`, nullable `status` / `exit_reason`, and nullable `mark_stale BOOLEAN`.

No natural key is invented. `opened_at` and `closed_at` remain nullable aware SQL instants, not availability or execution truth. `status` and `exit_reason` remain retained labels, not authenticated native position truth. `mark_stale` is retained as a nullable SQL boolean, not interpreted as a data-quality verdict. Prices and P&L remain retained finite binary64 values encoded exactly as hex; they are not economic-validity evidence.

A `closed_at` without `status="CLOSED"` is retained as an observation flag; it is not repaired, inferred, or treated as a close proof.

## Native path

`capture_positions` captures the entire exact-schema base table in one source transaction, with SQL count/text preflight, independent cell guards, and a max-plus-one row bound. `preserve_positions` performs two complete captures, verifies the reviewed snapshot pin, derives and bounds every projected record before append, and writes one event/artifact/batch through the actual native Bronze store and audit ledger.

The public reader verifies the original envelope, source/session scope, complete artifact, original batch, scoped job, and exact audit history. Current legacy SQL equality remains separate from retained native replay.

This package does not recover overwritten history or original provider bytes, authenticate instrument identity, prove closes or P&L, replay position execution, assert availability or economic validity, publish research, or grant decision eligibility.
