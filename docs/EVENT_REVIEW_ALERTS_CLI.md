# Event review alerts CLI

`event-review-alerts evaluate` evaluates event review alerts for open positions using the bounded event review alert manager.

## Contract

- Input: reviewed JSON payload with run ID, decision, and open positions.
- Output: receipt with `EVALUATED` or `NO_ALERT` status and alert payload.
- Safety: never asserts event truth, never grants decision eligibility, never enables live trading.

## Usage

```powershell
uv run python -m nse_quant.cli.event_review_alerts_cli evaluate `
  --db .\data\warehouse.duckdb `
  --input .\payload.json `
  --notify
```

## Rules

- Missing required fields are rejected.
- Decision must be an object.
- Open positions must be a list.
- Missing database or input file is rejected.
- Alert is emitted only on transition into review state and when open positions exist.
