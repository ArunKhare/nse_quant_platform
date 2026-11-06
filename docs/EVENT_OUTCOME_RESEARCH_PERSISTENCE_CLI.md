# Event outcome research persistence CLI

`event-outcome-research-persistence persist` persists a bounded event outcome research panel.

## Contract

- Input: reviewed JSON payload with panel ID, event ID, instrument, observation window, and panel payload.
- Output: receipt with `PERSISTED` or `REJECTED` status and persistence ID.
- Safety: never asserts event truth, never grants decision eligibility, never enables live trading.

## Usage

```powershell
uv run python -m nse_quant.cli.event_outcome_research_persistence_cli persist `
  --db .\data\warehouse.duckdb `
  --input .\payload.json `
  --enabled `
  --max-payload-bytes 65536
```

## Rules

- Missing required fields are rejected.
- Oversized payload is rejected.
- Panel must be an object.
- Persistence is idempotent through `INSERT OR REPLACE` on deterministic persistence ID.
