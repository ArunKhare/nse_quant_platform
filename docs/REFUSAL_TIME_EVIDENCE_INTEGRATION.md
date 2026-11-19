# Refusal-to-time-evidence integration

`integrate_refusal_into_time_evidence` integrates the refusal identity integration's output (`refusal_identity_integration.py`) into the independent time evidence evaluation (`independent_time_evidence.py`).

## Contract

- Input: refusal_identity_result dict, knowledge_cutoff str, economic_at str.
- Output: dict with integrated, reason, valid.
- Safety: never grants eligibility, never enables live trading.

## Rules

- Requires refusal_identity_result["integrated"] to be True (defaults to False if absent or non-bool).
- Requires knowledge_cutoff and economic_at to be non-empty strings.
- Requires knowledge_cutoff != economic_at (both axes remain separate).
- If refusal not integrated, returns integrated=False with reason REFUSAL_NOT_INTEGRATED_INTO_IDENTITY.
- Refuses non-dict refusal_identity_result, empty knowledge_cutoff, empty economic_at.
- Addresses the "integrate the refusal identity integration's output into the independent time evidence evaluation" sub-gap of gate 3 from docs/CURRENT_NATIVE_STATUS.md.
