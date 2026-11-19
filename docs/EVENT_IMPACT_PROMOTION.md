# Event impact promotion evaluator

`evaluate_promotion` consumes event outcome panel results and decides whether an
event impact rule qualifies for promotion to a hard eligibility gate.

## Contract

- Input: event outcomes list, regimes list, and `EventImpactPromotionSettings`.
- Output: promotion decision with status, reason, and metrics.
- Safety: never asserts event truth, never grants decision eligibility, never enables live trading.

## Rules

- Requires at least `min_events` outcomes.
- Requires at least `min_regimes` unique regimes.
- Requires adverse move rate at least `min_adverse_move_rate`.
- Requires IV crush rate at least `min_iv_crush_rate`.
- Requires mean spot return at most `max_mean_spot_return_pct`.
- `decision_eligibility_asserted` is always `False`.