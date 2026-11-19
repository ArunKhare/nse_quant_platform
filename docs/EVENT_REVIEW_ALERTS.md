# Event review alerts

`EventReviewAlertManager` emits at most one alert per transition into a `REVIEW_OPEN_POSITIONS` state when open positions exist.

## Contract

- Input: event-risk decision, open positions, and optional notifier.
- Output: persisted `event_review_alert` system event and optional notification.
- Stateful: consecutive review decisions do not repeat the alert.
- Rearm: an intervening non-review action re-arms the alert.

## Safety

- Advisory only; never places, modifies, or cancels orders.
- Never bypasses the persistent kill switch, paper mode, or risk controls.
- Never forces a position exit.
