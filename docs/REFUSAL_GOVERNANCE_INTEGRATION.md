# Refusal-to-governance integration

`integrate_refusal_into_governance` integrates the refusal acceptance integration's output (`refusal_acceptance_integration.py`) into the governance authority evaluation (`governance_authority.py`).

## Contract

- Input: refusal_acceptance_result dict, authority_claim dict, attestation dict, verification_key bytes.
- Output: dict with integrated, reason, authenticated.
- Safety: never grants eligibility, never enables live trading.

## Rules

- Requires refusal_acceptance_result["accepted"] to be True (defaults to False if absent or non-bool).
- If refusal not accepted, returns integrated=False with reason REFUSAL_NOT_ACCEPTED.
- If refusal accepted, delegates to authenticate_governance_authority(authority_claim=authority_claim, attestation=attestation, verification_key=verification_key).
- Refuses non-dict refusal_acceptance_result, non-dict authority_claim, non-dict attestation.
- Addresses the "integrate the refusal acceptance integration's output into the governance authority evaluation" sub-gap of gate 1 from docs/CURRENT_NATIVE_STATUS.md.
