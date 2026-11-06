# Event impact synthesis validation import CLI

`event-impact-synthesis-validation-import import` imports bounded event impact validation records from a reviewed JSON export.

## Contract

- Input: reviewed JSON export with event ID, instrument, and records.
- Output: receipt with `IMPORTED` or `REJECTED` status and imported count.
- Safety: never asserts event truth, never grants decision eligibility, never enables live trading.

## Usage

```powershell
uv run python -m nse_quant.cli.event_impact_synthesis_validation_import_cli import `
  --db .\data\warehouse.duckdb `
  --input .\export.json `
  --enabled `
  --max-records 100 `
  --max-input-bytes 1048576
```

## Rules

- Missing required fields are rejected.
- Records must be a list.
- Record count is bounded.
- Input size is bounded.
- Persistence is idempotent through `INSERT OR REPLACE` on deterministic persistence ID.
