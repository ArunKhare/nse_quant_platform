# Event impact synthesis validation vacuum CLI

`event-impact-synthesis-validation-vacuum vacuum` vacuums persisted event impact validation evidence.

## Contract

- Input: reviewed JSON payload with event ID and instrument.
- Output: receipt with `VACUUMED` or `REJECTED` status and vacuumed count.
- Safety: never asserts event truth, never grants decision eligibility, never enables live trading.

## Usage

```powershell
uv run python -m nse_quant.cli.event_impact_synthesis_validation_vacuum_cli vacuum `
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
