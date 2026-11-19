# Legacy feature-snapshots Silver

Persisted source-linked feature-snapshots Silver over the actual accepted feature-snapshots Bronze reader.

## Contract

- Store: `legacy-feature-snapshots-silver-recording@1`
- Command: `normalize.legacy_feature_snapshots@1`
- Contract: `silver.legacy_feature_snapshots /1/APPEND_REVISIONS`
- Each Silver revision is bound to the exact reviewed Bronze recording fingerprint and context hash.

## Retained materialization

All 22 source fields are materialized with exact nullability: `feature_id VARCHAR NOT NULL`; nullable `ts TIMESTAMPTZ`, `expiry DATE`, numeric `DOUBLE`/`BIGINT` fields, and `diagnostics VARCHAR` (declared retained JSON-cast text).

No invented natural key: only per-revision `feature_id` uniqueness plus ordinal. `run_id` is not a revision key. `regime` stays a retained legacy label, not native regime semantics. `diagnostics` stays exact nullable JSON-cast text; SQL NULL, JSON null text, and empty text remain distinct.

## Native path

`observe_feature_snapshots_bronze` reads Bronze records through the public Bronze reader and derives a bounded context. `persist_feature_snapshots_silver` requires two identical Bronze observations, then writes one Silver set, one observation per Bronze record, and one attempt, all inside one transaction with a separate audit job.

The public reader verifies the Silver context hash, recording fingerprint, and per-record coverage. Current Bronze equality remains separate from retained Silver replay.

This Silver does not interpret diagnostics as native evidence semantics, recompute native features, or grant decision eligibility.
