# Corporate-actions and earnings calendar

`src/nse_quant/research/corporate_actions_calendar.py` is a pure additive research registry for corporate actions (dividends, splits, bonuses, buybacks) and earnings events, consistent with the Trading Universe Roadmap Phase 2.

## Contract

- `CorporateAction` / `EarningsEvent` dataclasses with `decision_eligibility_asserted=False`.
- `is_earnings_blackout(as_of, earnings, settings)` returns True within the configured blackout window.
- `is_corporate_action_blackout(as_of, actions, settings)` returns True within the configured blackout window.
- `upcoming_earnings(as_of, earnings, days_ahead)` / `upcoming_corporate_actions(as_of, actions, days_ahead)` return sorted upcoming events.
- `build_calendar_summary(as_of, earnings, actions, settings)` returns the full payload with `decision_eligibility_asserted=False`.

## Safety

- Research registry only; no execution authority, no admission, no decision eligibility.
- `decision_eligibility_asserted=False` on every record, evaluation, and summary.
- Blackout flags are observational; they do not grant or gate anything.
