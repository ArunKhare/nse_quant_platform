# Event-risk policy CLI

`event-risk-policy evaluate` evaluates the event-risk policy using a reviewed JSON payload.

## Contract

- Input: reviewed JSON payload with optional `event_impact` and `reaction` objects.
- Output: receipt with `EVALUATED` or `REJECTED` status, action, size multiplier, and reasons.
- Safety: never asserts event truth, never grants decision eligibility, never enables live trading.

## Usage

```powershell
uv run python -m nse_quant.cli.event_risk_policy_cli evaluate `
  --input .\payload.json `
  --enabled `
  --reduce-size-on-high-volatility `
  --max-size-reduction-pct 50 `
  --review-iv-crush-threshold -0.02
```

## Rules

- Missing or invalid input file is rejected.
- `event_impact` and `reaction` must be objects if present.
- Disabled policy returns `OBSERVE` with size multiplier 1.0.
- `block_new_entries` true returns `BLOCK_NEW_ENTRIES` with size multiplier 0.0.
- High volatility with reduce enabled returns `REDUCE_SIZE` with configured multiplier.
- IV crush below threshold returns `REVIEW_OPEN_POSITIONS` with size multiplier 1.0.
