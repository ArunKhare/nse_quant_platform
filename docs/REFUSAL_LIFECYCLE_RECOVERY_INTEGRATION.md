# Refusal-to-lifecycle-recovery integration

`integrate_refusal_into_lifecycle_recovery` integrates the refusal admission integration's output (`refusal_admission_integration.py`) into the research lifecycle recovery evaluation (`research_lifecycle_recovery.py`).

## Contract

- Input: refusal_admission_result dict, original_obligations dict, recovery_outcomes dict.
- Output: dict with integrated, reason, reconciled.
- Safety: never grants eligibility, never enables live trading.

## Rules

- Requires refusal_admission_result["integrated"] to be True (defaults to False if absent or non-bool).
- If refusal not integrated, returns integrated=False with reason REFUSAL_NOT_INTEGRATED_INTO_ADMISSION.
- If refusal integrated, delegates to reconcile_lifecycle_recovery(original_obligations=original_obligations, recovery_outcomes=recovery_outcomes).
- Refuses non-dict refusal_admission_result, non-dict original_obligations, non-dict recovery_outcomes.
- Addresses the "integrate the refusal admission integration's output into the research lifecycle recovery evaluation" sub-gap of gate 5 from docs/CURRENT_NATIVE_STATUS.md.
