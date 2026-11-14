# Refusal-to-identity integration

`integrate_refusal_into_identity` integrates the refusal governance integration's output (`refusal_governance_integration.py`) into the identity binding revocation evaluation (`identity_binding_revocation.py`).

## Contract

- Input: refusal_governance_result dict, binding dict, revocation_record dict or None, verification_key bytes.
- Output: dict with integrated, reason, valid.
- Safety: never grants eligibility, never enables live trading.

## Rules

- Requires refusal_governance_result["integrated"] to be True (defaults to False if absent or non-bool).
- If refusal not integrated, returns integrated=False with reason REFUSAL_NOT_INTEGRATED_INTO_GOVERNANCE.
- If refusal integrated, delegates to validate_identity_binding(binding=binding, revocation_record=revocation_record, verification_key=verification_key).
- Refuses non-dict refusal_governance_result, non-dict binding.
- Addresses the "integrate the refusal governance integration's output into the identity binding revocation evaluation" sub-gap of gate 2 from docs/CURRENT_NATIVE_STATUS.md.
