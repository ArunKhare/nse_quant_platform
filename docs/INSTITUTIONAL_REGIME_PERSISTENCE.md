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


## Regime vocabulary

The physical table is `institutional_regime_evidence`. Its `regime_vocabulary` column distinguishes exact canonical registry labels (`canonical_v1`) from historical or noncanonical labels (`legacy_daily_v0`). Existing rows are retained and tagged as legacy during migration. This table remains observational; the vocabulary tag does not grant decision eligibility. No parallel `institutional_regime_observations` table is created.
