# Event impact synthesis persistence CLI

`event-impact-synthesis-persistence persist` persists a bounded event impact synthesis evidence record.

## Contract

- Input: reviewed JSON payload with synthesis ID, event ID, instrument, decision timestamp, and evidence payload.
- Output: receipt with `PERSISTED` or `REJECTED` status and persistence ID.
- Safety: never asserts event truth, never grants decision eligibility, never enables live trading.

## Usage

```powershell
uv run python -m nse_quant.cli.event_impact_synthesis_persistence_cli persist `
  --db .\data\warehouse.duckdb `
  --input .\payload.json `
  --enabled `
  --max-payload-bytes 65536
```

## Rules

- Missing required fields are rejected.
- Oversized payload is rejected.
- Evidence must be an object.
- Persistence is idempotent through `INSERT OR REPLACE` on deterministic persistence ID.
