# Event risk CLI

`event-risk evaluate` evaluates event risk for an instrument using the bounded event-risk plugin.

## Contract

- Input: reviewed JSON payload with run ID, instrument, and decision timestamp.
- Output: receipt with `EVALUATED` or `REJECTED` status and event-risk summary.
- Safety: never asserts event truth, never grants decision eligibility, never enables live trading.

## Usage

```powershell
uv run python -m nse_quant.cli.event_risk_cli evaluate `
  --db .\data\warehouse.duckdb `
  --input .\payload.json `
  --enabled `
  --block-new-entries `
  --blackout-minutes-before 30 `
  --blackout-minutes-after 30 `
  --allowed-event-types RBI_POLICY `
  --max-events 10
```

## Rules

- Missing required fields are rejected.
- Invalid timestamps are rejected.
- Missing database or input file is rejected.
- Only events within the configured blackout window are considered.
- Only explicitly allowed event types are considered.
- Only events whose affected underlyings include the instrument are matched.
- High-impact events with `block_new_entries` enabled produce `BLOCK_NEW_ENTRIES`.
