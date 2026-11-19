# Refusal-to-acceptance integration

`integrate_refusal_into_acceptance` integrates the refusal loop replay integration's output (`refusal_loop_replay_integration.py`) into the acceptance evaluation (`operational_acceptance.py`).

## Contract

- Input: refusal_loop_result dict, criteria AcceptanceCriteria.
- Output: AcceptanceDecision with accepted, reasons, checks, production_cutover_authorized, live_trading_authorized.
- Safety: never grants eligibility, never enables live trading.

## Rules

- Requires refusal_loop_result["integrated"] to be True (defaults to False if absent or non-bool).
- If refusal not integrated, returns accepted=False with reason REFUSAL_NOT_INTEGRATED_INTO_LOOP.
- If refusal integrated, delegates to evaluate_operational_acceptance(criteria=criteria).
- Refuses non-dict refusal_loop_result, non-AcceptanceCriteria criteria.
- Addresses the "integrate the refusal loop replay integration's output into the acceptance evaluation" sub-gap of gate 7 from docs/CURRENT_NATIVE_STATUS.md.
