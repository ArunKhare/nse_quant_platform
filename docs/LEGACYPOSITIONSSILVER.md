# Legacy positions Silver

`legacy_positions_silver_store.py` persists source-linked positions Silver over the actual Bronze reader.

## Contract

- Input: PositionsBronzePins (source_label, snapshot_id, capture_event_id, envelope_hash, recording_fingerprint), expected_context_sha256, actor_id, code_revision.
- Output: dict with revision_id, recording_fingerprint, row_count, job_id, decision_eligibility_asserted=False.
- Safety: no position truth, no broker/fill proof, no execution replay, no admission, no decision eligibility.

## Rules

- Materializes all 22 fields preserving nullability (TIMESTAMPTZ, DATE, DOUBLE hex, BIGINT/INTEGER, BOOLEAN, VARCHAR).
- First-write scope, no healing/adoption.
- Retained Silver vs current native Bronze vs current legacy SQL distinct.
