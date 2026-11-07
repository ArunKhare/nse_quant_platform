# Institutional regime evidence persistence

`persist_regime_evidence` persists the full regime payload with first-write semantics.

## Contract

- Input: regime payload dict, actor_id, code_revision.
- Output: evidence_id, as_of, symbol, classifier_version, regime_label, complete, recorded_at.
- Safety: never grants decision eligibility, never enables live trading.

## Rules

- First write per evidence_id only; repeat writes refused.
- Payload must contain as_of, symbol, classifier_version, regime_label, complete, components.
- Read roundtrip verifies the persisted payload.
