# Legacy decisions Silver

Persisted source-linked decisions Silver over the actual accepted Bronze reader.

## Contract

- Store: `legacy-decisions-silver-recording@1`
- Command: `normalize.legacy_decisions@1`
- Contract: `silver.legacy_decisions /1/APPEND_REVISIONS`
- Each Silver revision is bound to the exact reviewed Bronze recording fingerprint and context hash.

## Retained materialization

All nine source fields are materialized with exact nullability: `decision_id VARCHAR NOT NULL`; nullable `ts TIMESTAMPTZ`; nullable `expiry DATE`; nullable `run_id`, `decision_type`, `proposal_id`, `strategy`, `underlying`, and `payload VARCHAR` (declared retained JSON-cast text).

No invented natural key: only per-revision `decision_id` uniqueness plus ordinal. `decision_type` stays a retained legacy label, not native decision semantics. `payload` stays exact nullable JSON-cast text; SQL NULL, JSON null text, and empty text remain distinct.

## Native path

`observe_decisions_bronze` reads Bronze records through the public Bronze reader and derives a bounded context. `persist_decisions_silver` requires two identical Bronze observations, then writes one Silver set, one observation per Bronze record, and one attempt, all inside one transaction with a separate audit job.

The public reader verifies the Silver context hash, recording fingerprint, and per-record coverage. Current Bronze equality remains separate from retained Silver replay.

This Silver does not interpret decision_type or payload as native decision semantics, replay decision execution, or grant decision eligibility.
