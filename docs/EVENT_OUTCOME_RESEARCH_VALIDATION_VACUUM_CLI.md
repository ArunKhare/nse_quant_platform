# Event outcome research validation vacuum CLI

`event-outcome-research-validation-vacuum vacuum` vacuums persisted event outcome research evidence.

## Contract

- Input: reviewed JSON payload with event ID and instrument.
- Output: receipt with `VACUUMED` or `REJECTED` status and vacuumed count.
- Safety: never asserts event truth, never grants decision eligibility, never enables live trading.

## Usage

```powershell
uv run python -m nse_quant.cli.event_outcome_research_validation_vacuum_cli vacuum `
  --db .\data\warehouse.duckdb `
  --input .\payload.json `
  --enabled `
  --max-records 100
```

## Rules

- Missing required fields are rejected.
- Query is bounded by max records.
- Records are ordered by persisted_at descending.
- Vacuum is bounded by max records.
