# Legacy decisions Bronze

Audited preservation of the complete retained `main.decisions` base table.

## Contract

- Codec: `legacy-decisions-snapshot@1`
- Projection: `legacy-decision-observation@1`
- Recording: `legacy-decisions-bronze-recording@1`
- Command: `migrate.legacy_decisions@1`
- Source: `legacy_decisions_table_snapshot`, `origin_kind=legacy_snapshot`

## Retained source

The exact nine-column source is:

- `decision_id VARCHAR PRIMARY KEY`
- `ts TIMESTAMPTZ`
- `run_id VARCHAR`
- `decision_type VARCHAR`
- `proposal_id VARCHAR`
- `strategy VARCHAR`
- `underlying VARCHAR`
- `expiry DATE`
- `payload JSON`

Only `decision_id` is the retained key. All other fields remain nullable, and no natural key is invented across run, type, proposal, strategy, underlying, expiry, or time.

`ts` remains a nullable aware SQL instant; it is not availability or economic validity. `expiry` remains a retained calendar date only. `decision_type` remains a retained label, not authenticated native decision semantics. `payload` remains exact nullable `CAST(JSON AS VARCHAR)` text; SQL `NULL`, JSON `null` text, and empty text remain distinct.

## Native path

`capture_decisions` captures the entire exact-schema base table in one source transaction, with SQL count/text preflight, independent cell guards, and a max-plus-one row bound. `preserve_decisions` performs two complete captures, verifies the reviewed snapshot pin, derives and bounds every projected record before append, and writes one event/artifact/batch through the actual native Bronze store and audit ledger.

The public reader verifies the original envelope, source/session scope, complete artifact, original batch, scoped job, and exact audit history. Current legacy SQL equality remains separate from retained native replay.

This package does not recover overwritten history or original provider bytes, replay decisions, assert availability or economic validity, publish research, or grant decision eligibility.
