# Refusal acceptance closure integration

`integrate_closed_loop_into_acceptance` integrates the closed loop's output (`refusal_loop_closure_integration.py`) back into the operational acceptance evaluation (`operational_acceptance.py`) to complete the full integrated and operational acceptance.

## Contract

- Input: closed_loop_result dict, criteria AcceptanceCriteria.
- Output: AcceptanceDecision with accepted, reasons, checks, production_cutover_authorized, live_trading_authorized.
- Safety: never grants eligibility, never enables live trading.

## Rules

- Requires closed_loop_result["closed"] to be True (defaults to False if absent or non-bool).
- If loop not closed, returns accepted=False with reason REFUSAL_LOOP_NOT_CLOSED.
- If loop closed, delegates to evaluate_operational_acceptance(criteria=criteria).
- Refuses non-dict closed_loop_result, non-AcceptanceCriteria criteria.
- Addresses the "integrate the closed loop's output back into the operational acceptance evaluation to complete the full integrated and operational acceptance" sub-gap of gate 7 from docs/CURRENT_NATIVE_STATUS.md.
