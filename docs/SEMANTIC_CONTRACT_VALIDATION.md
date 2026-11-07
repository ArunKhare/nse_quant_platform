# Semantic contract validation

`validate_semantic_contracts` validates that mapped fields actually satisfy each requirement's semantic contract.

## Contract

- Input: candidate dict.
- Output: dict with valid, reason, violations (requirement -> list of issue codes).
- Safety: never grants eligibility, never enables live trading.

## Rules

- Valid only when all mapped fields satisfy their semantic validators.
- Violations reported per requirement with MISSING_FIELD or INVALID_VALUE codes.
- Refuses non-dict candidate.
- Addresses the "semantic contract validation" sub-gap of gate 6 from docs/CURRENT_NATIVE_STATUS.md.
