# Event impact synthesis validation persistence CLI

`event-impact-synthesis-validation-persistence persist` persists a bounded event impact validation record.

## Contract

- Input: reviewed JSON payload with validation ID, synthesis ID, event ID, instrument, decision timestamp, and validation payload.
- Output: receipt with `PERSISTED` or `REJECTED` status and persistence ID.
- Safety: never asserts event truth, never grants decision eligibility, never enables live trading.

## Usage

```powershell
uv run python -m nse_quant.cli.event_impact_synthesis_validation_persistence_cli persist `
  --db .\data\warehouse.duckdb `
  --input .\payload.json `
  --enabled `
  --max-payload-bytes 65536
```

## Rules

- Missing required fields are rejected.
- Oversized payload is rejected.
- Validation must be an object.
- Persistence is idempotent through `INSERT OR REPLACE` on deterministic persistence ID.
