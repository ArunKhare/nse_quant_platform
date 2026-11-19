# New sufficient eligible publication/admission contract

`evaluate_admission_contract` evaluates a publication/admission request against a new sufficient contract combining authority, identity, temporal evidence, and lifecycle checks, while preserving the existing research @1's rejection of POINT_IN_TIME_DECISION.

## Contract

- Input: `AdmissionRequest` (namespace, authority_id, underlying, derivative, knowledge_cutoff, economic_at, request_kind), plus four boolean flags (authority_authenticated, identity_valid, temporal_matched, lifecycle_resolved).
- Output: `AdmissionDecision` with eligible, reasons, checks.
- Safety: never enables live trading, never bypasses the kill switch.

## Rules

- Rejects POINT_IN_TIME_DECISION unconditionally (preserving existing research @1 behavior).
- Requires all four flags True for eligibility.
- Addresses gate 4 from docs/CURRENT_NATIVE_STATUS.md.
