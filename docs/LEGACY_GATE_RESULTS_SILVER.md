# Legacy gate-results Silver

Persisted, source-linked Silver for the separately accepted `gate_results` Bronze family.

## Contract

- Store: `legacy-gate-results-silver-recording@1`
- Command: `normalize.legacy_gate_results@1`
- Dataset: `silver.legacy_gate_results_observations` / `1` / `APPEND_REVISIONS`
- Source: actual `legacy_gate_results_bronze.read_gate_results_bronze` and original-recording reader

## Retained semantics

All nine source fields are materialized with their retained nullability:

- `gate_result_id` is the only retained key and is non-null.
- `ts` remains a nullable aware SQL instant; it is never treated as availability.
- `passed` remains exact nullable `True`, `False`, or SQL `NULL`; it is not native approval.
- `reason` remains opaque nullable text.
- `details` remains exact nullable `CAST(JSON AS VARCHAR)` text; SQL `NULL`, JSON `null` text, and empty text remain distinct.

No natural key is invented across `run_id`, `proposal_id`, `strategy`, `gate`, or time. Silver enforces only `(revision_id, ordinal)` and `(revision_id, gate_result_id)` uniqueness.

## Scope and obligations

The first-write scope is the native capture event, excluding source label and other review pins. The producer reads the pinned Bronze recording twice, reconstructs the complete snapshot and every ordinal, performs independent record/scalar/aggregate SQL preflight, and writes the revision atomically before a separate final audit.

Retained Silver, current native Bronze, and current legacy SQL remain distinct observations. This package adds no gate interpretation, original gate replay, admission, publication, decision eligibility, or positive trading lane.
