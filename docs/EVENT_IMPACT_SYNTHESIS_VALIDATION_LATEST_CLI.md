# Event impact synthesis validation latest CLI

`event-impact-synthesis-validation-latest latest` returns the latest persisted event impact validation evidence.

## Contract

- Input: reviewed JSON payload with event ID and instrument.
- Output: receipt with `LATEST` or `REJECTED` status and latest record.
- Safety: never asserts event truth, never grants decision eligibility, never enables live trading.

## Usage

```powershell
uv run python -m nse_quant.cli.event_impact_synthesis_validation_latest_cli latest `
  --db .\data\warehouse.duckdb `
  --input .\payload.json `
  --enabled `
  --max-records 1
```

## Rules

- Missing required fields are rejected.
- Query is bounded by max records.
- Records are ordered by persisted_at descending.
- Latest is bounded by max records.
