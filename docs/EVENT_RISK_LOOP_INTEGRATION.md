# Event-risk decision-loop integration

Wires the advisory `EventRiskPolicy` into the paper decision loop after a proposal is generated and before the signal decision is persisted.

## Behavior

- Reads `event_impact` evidence for the current decision cycle.
- Evaluates the event-risk policy.
- Persists an `event_risk_policy` decision record.
- `BLOCK_NEW_ENTRIES` finishes the cycle as `event_risk_blocked`; no order is submitted.
- `REDUCE_SIZE` scales proposal leg lots by the configured multiplier, with a floor of one lot per leg.
- `OBSERVE` leaves the proposal unchanged.

## Safety

- Advisory policy only; it never bypasses the kill switch, paper mode, or other risk controls.
- A blocked cycle does not submit an order.
- Size reduction never zeroes leg lots.
- The integration is idempotent and fails with a clear anchor error rather than making a partial edit.
