# Event impact synthesis validation optimize CLI

`event-impact-synthesis-validation-optimize optimize` optimizes persisted event impact validation evidence.

## Contract

- Input: reviewed JSON payload with event ID and instrument.
- Output: receipt with `OPTIMIZED` or `REJECTED` status and optimized count.
- Safety: never asserts event truth, never grants decision eligibility, never enables live trading.

## Usage

```powershell
uv run python -m nse_quant.cli.event_impact_synthesis_validation_optimize_cli optimize `
  --db .\data\warehouse.duckdb `
  --input .\payload.json `
  --enabled `
  --max-records 100
```

## Rules

- Missing required fields are rejected.
- Query is bounded by max records.
- Records are ordered by persisted_at descending.
- Optimize is bounded by max records.
