# Refusal replay reconciliation

`reconcile_refusal_replay` validates that only stages that actually ran (kill_switch, safety_boundary, publication_admission, native_inputs) are replayed, matching the refusal-only contract in `native_refusal_decision.py`.

## Contract

- Input: replayed_stages tuple, stage_outcomes dict.
- Output: dict with reconciled, reason, violations (list of issue codes).
- Safety: never grants eligibility, never enables live trading.

## Rules

- Replayed stages must be a subset of RAN_STAGES (not NOT_RUN_STAGES).
- Stage outcomes must only have keys for RAN_STAGES.
- Refuses non-tuple replayed_stages, non-dict stage_outcomes.
- Addresses the "complete exact replay of stages that actually run" sub-gap of gate 6 from docs/CURRENT_NATIVE_STATUS.md.
