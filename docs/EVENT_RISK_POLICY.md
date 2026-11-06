# Event-aware risk policy

`evaluate_event_risk` produces a conservative, explainable risk recommendation from event-impact evidence and an optional observed reaction.

## Contract

- Input: event-impact payload, optional reaction payload, and `EventRiskPolicySettings`.
- Output: `EventRiskDecision` with action, size multiplier, and reasons.
- Actions: `OBSERVE`, `REDUCE_SIZE`, `BLOCK_NEW_ENTRIES`, `REVIEW_OPEN_POSITIONS`.
- `decision_eligibility_asserted` is always `False`.

## Rules

- Disabled policy always returns `OBSERVE` with multiplier 1.0.
- `block_new_entries` returns `BLOCK_NEW_ENTRIES` with multiplier 0.0.
- High volatility impact returns `REDUCE_SIZE` with the configured multiplier when reduction is enabled.
- IV crush at or below the threshold returns `REVIEW_OPEN_POSITIONS` with multiplier 1.0.
- Missing inputs are safe and return `OBSERVE`.

## Safety

- Advisory only; never places, modifies, or cancels orders.
- Never bypasses the persistent kill switch, paper mode, or risk controls.
- Never forces a position exit.
