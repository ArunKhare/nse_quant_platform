# Input completeness validation

`validate_input_completeness` validates a dict of supplied inputs against the 9 requirements in `native_strategy_requirements.py`, returning which are present/missing.

## Contract

- Input: supplied_inputs dict.
- Output: dict with complete, reason, present, missing.
- Safety: never grants eligibility, never enables live trading.

## Rules

- Complete only when all 9 required keys are present.
- Refuses non-dict input.
- Addresses the "complete required native strategy/analytics inputs" sub-gap of gate 6 from docs/CURRENT_NATIVE_STATUS.md.
