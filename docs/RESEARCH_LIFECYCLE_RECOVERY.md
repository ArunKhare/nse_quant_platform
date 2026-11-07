# Research lifecycle/recovery classification

`classify_obligation` classifies research obligations into lifecycle states and explicitly refuses to heal failed, incomplete, unlinked, or orphan obligations by later success.

## Contract

- Input: obligation dict (obligation_id, status, linked, result).
- Output: `LifecycleClassification` with obligation_id, state, healable, reason.
- Safety: never enables live trading, never grants decision eligibility.

## States

- PENDING: healable, awaiting result.
- FAILED: not healable.
- INCOMPLETE: not healable.
- UNLINKED: not healable.
- ORPHAN: not healable.
- RESOLVED: healable, with linked result.
