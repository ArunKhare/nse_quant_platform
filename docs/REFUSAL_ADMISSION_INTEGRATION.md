# Refusal-to-admission integration

`integrate_refusal_into_admission` integrates the refusal time evidence integration's output (`refusal_time_evidence_integration.py`) into the eligible admission contract evaluation (`eligible_admission_contract.py`).

## Contract

- Input: refusal_time_evidence_result dict, request AdmissionRequest, authority_authenticated bool, identity_valid bool, temporal_matched bool, lifecycle_resolved bool.
- Output: dict with integrated, reason, eligible.
- Safety: never grants eligibility, never enables live trading.

## Rules

- Requires refusal_time_evidence_result["integrated"] to be True (defaults to False if absent or non-bool).
- If refusal not integrated, returns integrated=False with reason REFUSAL_NOT_INTEGRATED_INTO_TIME_EVIDENCE.
- If refusal integrated, delegates to evaluate_admission_contract(request=request, authority_authenticated=authority_authenticated, identity_valid=identity_valid, temporal_matched=temporal_matched, lifecycle_resolved=lifecycle_resolved).
- Preserves existing research @1 rejection of POINT_IN_TIME_DECISION.
- Refuses non-dict refusal_time_evidence_result, non-AdmissionRequest request.
- Addresses the "integrate the refusal time evidence integration's output into the eligible admission contract evaluation" sub-gap of gate 4 from docs/CURRENT_NATIVE_STATUS.md.
