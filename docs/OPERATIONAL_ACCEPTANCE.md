# Full integrated and operational acceptance

`evaluate_operational_acceptance` evaluates a set of acceptance criteria (package QA passed, integration tests passed, operational checks passed) and returns an acceptance decision, without granting production cutover or live trading.

## Contract

- Input: `AcceptanceCriteria` (package_qa_passed, integration_tests_passed, operational_checks_passed).
- Output: `AcceptanceDecision` with accepted, reasons, checks, production_cutover_authorized (always False), live_trading_authorized (always False).
- Safety: never grants production cutover, never enables live trading.

## Rules

- Accepted only when all three criteria pass.
- Refuses invalid criteria.
- Addresses gate 7 from docs/CURRENT_NATIVE_STATUS.md.
