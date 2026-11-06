# Event impact synthesis validation export CLI

`event-impact-synthesis-validation-export export` exports persisted event impact validation evidence to a JSON file.

## Contract

- Input: reviewed JSON payload with event ID and instrument.
- Output: receipt with `EXPORTED` or `REJECTED` status and output path.
- Safety: never asserts event truth, never grants decision eligibility, never enables live trading.

## Usage

```powershell
uv run python -m nse_quant.cli.event_impact_synthesis_validation_export_cli export `
  --db .\data\warehouse.duckdb `
  --input .\payload.json `
  --output .\export.json `
  --enabled `
  --max-records 100 `
  --max-output-bytes 1048576
```

## Rules

- Missing required fields are rejected.
- Query is bounded by max records.
- Output is bounded by max output bytes.
- Records are ordered by persisted_at descending.
