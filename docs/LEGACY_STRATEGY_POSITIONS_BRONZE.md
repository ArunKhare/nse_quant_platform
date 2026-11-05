# Legacy strategy positions Bronze

Audited preservation of the complete retained `main.strategy_positions` base table.

## Contract

- Codec: `legacy-strategy-positions-snapshot@1`
- Projection: `legacy-strategy-position-observation@1`
- Recording: `legacy-strategy-positions-bronze-recording@1`
- Command: `migrate.legacy_strategy_positions@1`
- Source: `legacy_strategy_positions_table_snapshot`, `origin_kind=legacy_snapshot`

## Retained source

The exact 16-column source is retained: `strategy_position_id` sole primary key; nullable `proposal_id`, `strategy`, `underlying`, and `expiry DATE`; nullable aware `opened_at` / `closed_at`; finite binary64 `entry_price`, `current_price`, `realized_pnl`, and `unrealized_pnl`; nullable `status` and `exit_reason`; opaque JSON `all_triggered_exits`; nullable `thesis`; and opaque JSON `metadata`.

No natural key is invented. Instants remain nullable aware SQL instants, not availability or execution truth. `status` and `exit_reason` remain retained labels, not authenticated native position truth. Prices and P&L remain retained finite binary64 values encoded exactly as hex—not economic-validity evidence. `all_triggered_exits`, `thesis`, and `metadata` remain opaque JSON-cast text; SQL `NULL`, JSON `null` text, and empty text remain distinct.

A `closed_at` without `status="CLOSED"` is retained as an observation flag; it is not repaired, inferred, or treated as a close proof.

## Native path

`capture_strategy_positions` captures the entire exact-schema base table in one source transaction, with SQL count/text preflight, independent cell guards, and a max-plus-one row bound. `preserve_strategy_positions` performs two complete captures, verifies the reviewed snapshot pin, derives and bounds every projected record before append, and writes one event/artifact/batch through the actual native Bronze store and audit ledger.

The public reader verifies the original envelope, source/session scope, complete artifact, original batch, scoped job, and exact audit history. Current legacy SQL equality remains separate from retained native replay.

This package does not recover overwritten history or original provider bytes, prove closes or P&L, interpret exits, thesis, or metadata, replay position execution, assert availability or economic validity, publish research, or grant decision eligibility.
