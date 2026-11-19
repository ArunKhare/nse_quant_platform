# Legacy evidence-snapshots Silver

Persisted source-linked evidence-snapshots Silver over the actual accepted evidence-snapshots Bronze reader.

## Contract

- Store: `legacy-evidence-snapshots-silver-recording@1`
- Command: `normalize.legacy_evidence_snapshots@1`
- Contract: `silver.legacy_evidence_snapshots /1/APPEND_REVISIONS`
- Each Silver revision is bound to the exact reviewed Bronze recording fingerprint and context hash.

## Retained materialization

All five source fields are materialized with exact nullability: `run_id VARCHAR NOT NULL`; `ts TIMESTAMPTZ NOT NULL`; nullable `symbol VARCHAR`; `plugin_name VARCHAR NOT NULL`; nullable `payload_json VARCHAR` (declared retained JSON-cast text).

The retained natural key is `(run_id, ts, plugin_name)`, independent of nullable `symbol`. `payload_json` stays exact nullable JSON-cast text; SQL NULL, JSON null text, and empty text remain distinct.

## Native path

`observe_evidence_snapshots_bronze` reads Bronze records through the public Bronze reader and derives a bounded context. `persist_evidence_snapshots_silver` requires two identical Bronze observations, then writes one Silver set, one observation per Bronze record, and one attempt, all inside one transaction with a separate audit job.

The public reader verifies the Silver context hash, recording fingerprint, and per-record coverage. Current Bronze equality remains separate from retained Silver replay.

This Silver does not interpret payload_json as native evidence semantics, replay evidence generation, or grant decision eligibility.
