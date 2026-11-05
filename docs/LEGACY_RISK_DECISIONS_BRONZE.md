# Legacy risk-decisions Bronze

Audited preservation of the complete retained `main.risk_decisions` base table.

## Contract

- Codec: `legacy-risk-decisions-snapshot@1`
- Projection: `legacy-risk-decision-observation@1`
- Recording: `legacy-risk-decisions-bronze-recording@1`
- Command: `migrate.legacy_risk_decisions@1`
- Source: `legacy_risk_decisions_table_snapshot`, `origin_kind=legacy_snapshot`

## Retained source

The exact eight-column source is:

- `risk_decision_id VARCHAR PRIMARY KEY`
- `ts TIMESTAMPTZ`
- `run_id VARCHAR`
- `proposal_id VARCHAR`
- `strategy VARCHAR`
- `approved BOOLEAN`
- `reasons JSON`
- `checks JSON`

Only `risk_decision_id` is the retained key. All other fields remain nullable, and no natural key is invented across run, proposal, strategy, time, or approval state.

`approved` is the exact retained nullable boolean. It is a legacy claim, not native risk approval, safety truth, publication, or permission to trade. `reasons` and `checks` remain exact nullable `CAST(JSON AS VARCHAR)` text; SQL `NULL`, JSON `null` text, and empty text remain distinct. No payload is parsed, normalized, or interpreted.

## Native path

`capture_risk_decisions` captures the entire exact-schema base table in one source transaction, with SQL count/text preflight, independent cell guards, and a max-plus-one row bound. `preserve_risk_decisions` performs two complete captures, verifies the reviewed snapshot pin, derives and bounds every projected record before append, and writes one event/artifact/batch through the actual native Bronze store and audit ledger.

The public reader verifies the original envelope, source/session scope, complete artifact, original batch, scoped job, and exact audit history. Current legacy SQL equality remains separate from retained native replay.

This package does not recover overwritten history or original provider bytes, replay risk execution, assert availability or economic validity, publish research, or grant decision eligibility.
