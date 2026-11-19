# Research lifecycle recovery reconciliation

`reconcile_lifecycle_recovery` validates that a research lifecycle recovery doesn't heal original failed, incomplete, unlinked, or orphan obligations by later success.

## Contract

- Input: original_obligations dict (obligation_id -> state), recovery_outcomes dict (obligation_id -> state).
- Output: dict with reconciled, reason, violations (list of issue codes).
- Safety: never grants eligibility, never enables live trading.

## Rules

- Original obligations must have valid states (failed, incomplete, unlinked, orphan).
- Recovery must not heal original failed/incomplete/unlinked/orphan obligations (recovery state must not be "resolved" for an obligation with an invalid original state).
- Refuses non-dict original_obligations, non-dict recovery_outcomes.
- Addresses the "research lifecycle/recovery beyond bounded first-write profiles" sub-gap of gate 5 from docs/CURRENT_NATIVE_STATUS.md.
