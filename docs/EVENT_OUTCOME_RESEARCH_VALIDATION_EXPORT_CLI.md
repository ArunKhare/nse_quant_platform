# Event outcome research validation export CLI

`event-outcome-research-validation-export export` exports persisted event outcome research evidence to CSV.

## Contract

- Input: reviewed JSON payload with event ID and instrument.
- Output: CSV file with exported records.
- Receipt: `EXPORTED` or `REJECTED` status and exported count.
- Safety: never asserts event truth, never grants decision eligibility, never enables live trading.

## Usage

```powershell
uv run python -m nse_quant.cli.event_outcome_research_validation_export_cli export `
  --db .\data\warehouse.duckdb `
  --input .\payload.json `
  --output .\export.csv `
  --enabled `
  --max-records 100
```

## Rules

- Missing required fields are rejected.
- Query is bounded by max records.
- Records are ordered by persisted_at descending.
- Export is bounded by max records.
