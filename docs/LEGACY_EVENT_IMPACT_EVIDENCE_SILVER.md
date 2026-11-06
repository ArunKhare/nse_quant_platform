# Legacy event impact evidence Silver

Persisted source-linked event-impact-evidence Silver over the actual accepted Bronze reader.

## Contract

- Store: `legacy-event-impact-evidence-silver-recording@1`
- Command: `normalize.legacy_event_impact_evidence@1`
- Contract: `silver.legacy_event_impact_evidence /1/APPEND_REVISIONS`
- Each Silver revision is bound to the exact reviewed Bronze recording fingerprint and context hash.

## Retained materialization

All thirteen source fields are materialized with exact nullability: `impact_id VARCHAR NOT NULL`; nullable `ts TIMESTAMPTZ`; nullable `confidence DOUBLE`; nullable `run_id`, `event_id`, `event_type`, `instrument`, `direction`, `volatility_impact`, `liquidity_impact`, `surprise_label`, `recommended_action`, and `payload VARCHAR` (declared retained JSON-cast text).

No invented natural key: only per-revision `impact_id` uniqueness plus ordinal. `direction`, `volatility_impact`, `liquidity_impact`, `surprise_label`, and `recommended_action` stay opaque nullable legacy labels. `payload` stays exact nullable JSON-cast text; SQL NULL, JSON null text, and empty text remain distinct.

## Native path

`observe_event_impact_evidence_bronze` reads Bronze records through the public Bronze reader and derives a bounded context. `persist_event_impact_evidence_silver` requires two identical Bronze observations, then writes one Silver set, one observation per Bronze record, and one attempt, all inside one transaction with a separate audit job.

The public reader verifies the Silver context hash, recording fingerprint, and per-record coverage. Current Bronze equality remains separate from retained Silver replay.

This Silver does not interpret impact labels or payloads as native event truth, replay impact synthesis, or grant decision eligibility.
