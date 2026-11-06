# Event impact synthesis validation exists CLI

`event-impact-synthesis-validation-exists exists` checks whether persisted event impact validation evidence exists.

## Contract

- Input: reviewed JSON payload with event ID and instrument.
- Output: receipt with `EXISTS` or `REJECTED` status and exists flag.
- Safety: never asserts event truth, never grants decision eligibility, never enables live trading.

## Usage

```powershell
uv run python -m nse_quant.cli.event_impact_synthesis_validation_exists_cli exists `
  --db .\data\warehouse.duckdb `
  --input .\payload.json `
  --enabled `
  --max-records 1
```

## Rules

- Missing required fields are rejected.
- Query is bounded by max records.
- Records are ordered by persisted_at descending.
- Exists is bounded by max records.
