# Refusal loop closure integration

`close_refusal_loop` integrates the research lifecycle recovery evaluation's output (`research_lifecycle_recovery.py`) back into the refusal loop replay integration (`refusal_loop_replay_integration.py`) to close the loop.

## Contract

- Input: refusal_result dict, lifecycle_recovery_result dict, existing_audited (optional AuditedDecision).
- Output: dict with closed, reason, loop_result.
- Safety: never grants eligibility, never enables live trading.

## Rules

- Requires lifecycle_recovery_result["reconciled"] to be True (defaults to False if absent or non-bool).
- If lifecycle recovery not reconciled, returns closed=False with reason LIFECYCLE_RECOVERY_NOT_RECONCILED.
- If lifecycle recovery reconciled, delegates to integrate_refusal_into_loop(refusal_result=refusal_result, existing_audited=existing_audited).
- Refuses non-dict refusal_result, non-dict lifecycle_recovery_result.
- Addresses the "integrate the research lifecycle recovery evaluation's output back into the refusal loop replay integration to close the loop" sub-gap of gate 6 from docs/CURRENT_NATIVE_STATUS.md.
