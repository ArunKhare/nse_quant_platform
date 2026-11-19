# Legacy strategy-positions Silver

`legacy_strategy_positions_silver_store.py` persists source-linked strategy-positions Silver over the actual Bronze reader.

## Contract

- Input: StrategyPositionsBronzePins, expected_context_sha256, actor_id, code_revision.
- Output: dict with revision_id, recording_fingerprint, row_count, job_id, decision_eligibility_asserted=False.
- Safety: no position truth, no broker/fill proof, no execution replay, no admission, no decision eligibility.

## Rules

- Materializes all 16 fields preserving nullability; preserves SQL NULL vs JSON null text for all_triggered_exits/metadata.
- First-write scope, no healing/adoption.
- Retained Silver vs current native Bronze vs current legacy SQL distinct.
