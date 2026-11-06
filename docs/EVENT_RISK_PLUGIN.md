# Event risk plugin

`EventRiskPlugin` queries reviewed market events in a look-ahead-safe window and synthesizes observational event-risk evidence.

## Contract

- Input: run ID, instrument, and decision timestamp.
- Output: event-risk summary with `blocked_new_entries`, matched event count, and evidence payloads.
- Safety: never asserts event truth, never grants decision eligibility, never enables live trading.

## Rules

- Disabled plugin returns unavailable with `event_risk_disabled`.
- Decision timestamp must be timezone-aware.
- Only events within the configured blackout window are considered.
- Only explicitly allowed event types are considered.
- Only events whose affected underlyings include the instrument are matched.
- High-impact events with `block_new_entries` enabled produce `BLOCK_NEW_ENTRIES`.
- Evidence is persisted into `event_impact_evidence` with deterministic impact ID.
