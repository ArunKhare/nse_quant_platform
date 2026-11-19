# Event outcome research validation exists CLI

`event-outcome-research-validation-exists exists` checks whether persisted event outcome research evidence exists.

## Contract

- Input: reviewed JSON payload with event ID and instrument.
- Output: receipt with `EXISTS`, `NOT_FOUND`, or `REJECTED` status and count.
- Safety: never asserts event truth, never grants decision eligibility, never enables live trading.

## Usage

```powershell
uv run python -m nse_quant.cli.event_outcome_research_validation_exists_cli exists `
  --db .\data\warehouse.duckdb `
  --input .\payload.json `
  --enabled `
  --max-records 100
```

## Rules

- Missing required fields are rejected.
- Query is bounded by max records.
- Records are ordered by persisted_at descending.
- Exists check is bounded by max records.