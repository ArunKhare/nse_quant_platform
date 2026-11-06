# Legacy risk decisions Silver

Persisted source-linked risk-decisions Silver over the actual accepted Bronze reader.

## Contract

- Store: `legacy-risk-decisions-silver-recording@1`
- Command: `normalize.legacy_risk_decisions@1`
- Contract: `silver.legacy_risk_decisions /1/APPEND_REVISIONS`
- Each Silver revision is bound to the exact reviewed Bronze recording fingerprint and context hash.

## Retained materialization

All eight source fields are materialized with exact nullability: `risk_decision_id VARCHAR NOT NULL`; nullable `ts TIMESTAMPTZ`; nullable `approved BOOLEAN`; nullable `run_id`, `proposal_id`, `strategy`, `reasons`, and `checks VARCHAR` (declared retained JSON-cast text).

No invented natural key: only per-revision `risk_decision_id` uniqueness plus ordinal. `approved` retains exact True/False/None; retained True is a legacy claim, not native risk approval. `reasons` and `checks` stay exact nullable JSON-cast text; SQL NULL, JSON null text, and empty text remain distinct.

## Native path

`observe_risk_decisions_bronze` reads Bronze records through the public Bronze reader and derives a bounded context. `persist_risk_decisions_silver` requires two identical Bronze observations, then writes one Silver set, one observation per Bronze record, and one attempt, all inside one transaction with a separate audit job.

The public reader verifies the Silver context hash, recording fingerprint, and per-record coverage. Current Bronze equality remains separate from retained Silver replay.

This Silver does not interpret reasons or checks, treat approved=True as native risk approval, replay risk execution, or grant decision eligibility.
