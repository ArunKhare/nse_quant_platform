# Legacy gate results Silver

Persisted source-linked gate-results Silver over the actual accepted Bronze reader.

## Contract

- Store: `legacy-gate-results-silver-recording@1`
- Command: `normalize.legacy_gate_results@1`
- Contract: `silver.legacy_gate_results /1/APPEND_REVISIONS`
- Each Silver revision is bound to the exact reviewed Bronze recording fingerprint and context hash.

## Retained materialization

All nine source fields are materialized with exact nullability: `gate_result_id VARCHAR NOT NULL`; nullable `ts TIMESTAMPTZ`, `run_id`, `proposal_id`, `strategy`, `gate`, `passed BOOLEAN`, `reason`, and `details VARCHAR` (declared retained JSON-cast text).

No invented natural key: only per-revision `gate_result_id` uniqueness plus ordinal. `passed` retains exact True/False/None; retained True is not native approval. `reason` stays opaque nullable text; `details` stays exact nullable JSON-cast text. SQL NULL, JSON null text, and empty text remain distinct.

## Native path

`observe_gate_results_bronze` reads Bronze records through the public Bronze reader and derives a bounded context. `persist_gate_results_silver` requires two identical Bronze observations, then writes one Silver set, one observation per Bronze record, and one attempt, all inside one transaction with a separate audit job.

The public reader verifies the Silver context hash, recording fingerprint, and per-record coverage. Current Bronze equality remains separate from retained Silver replay.

This Silver does not parse gate details/reasons as native policy truth, treat passed=True as approval, or grant decision eligibility.
