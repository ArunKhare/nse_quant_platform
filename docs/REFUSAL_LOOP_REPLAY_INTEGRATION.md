# Refusal-to-full-loop-replay integration

`integrate_refusal_into_loop` integrates the refusal kernel's audited record (from `refusal_audited_record.py`) into the full decision loop replay (`full_decision_loop_replay.py`).

## Contract

- Input: refusal_result dict, existing_audited (optional AuditedDecision).
- Output: dict with integrated, reason, audited, existing_audited.
- Safety: never grants eligibility, never enables live trading.

## Rules

- Integrated when refusal_audited.recorded is True and (existing_audited is None or existing_audited.recorded is True).
- Refuses non-dict refusal_result.
- Addresses the "integrate the audited record back into the full stage-chain replay" sub-gap of gate 6 from docs/CURRENT_NATIVE_STATUS.md.
