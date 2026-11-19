# Event impact synthesis validation truncate CLI

`event-impact-synthesis-validation-truncate truncate` truncates persisted event impact validation evidence.

## Contract

- Input: reviewed JSON payload with event ID and instrument.
- Output: receipt with `TRUNCATED` or `REJECTED` status and truncated count.
- Safety: never asserts event truth, never grants decision eligibility, never enables live trading.

## Usage

```powershell
uv run python -m nse_quant.cli.event_impact_synthesis_validation_truncate_cli truncate `
  --db .\data\warehouse.duckdb `
  --input .\payload.json `
  --enabled `
  --max-records 100
```

## Rules

- Missing required fields are rejected.
- Query is bounded by max records.
- Records are ordered by persisted_at descending.
- Truncate is bounded by max records.
