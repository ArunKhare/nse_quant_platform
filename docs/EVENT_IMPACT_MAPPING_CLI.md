# Event impact mapping CLI

`event-impact-mapping map` maps a reviewed market event to instrument impact evidence using the event impact mapper.

## Contract

- Input: reviewed JSON payload with event ID, instrument, and decision timestamp.
- Output: receipt with `MAPPED` or `REJECTED` status and mapping payload.
- Safety: never asserts event truth, never grants decision eligibility, never enables live trading.

## Usage

```powershell
uv run python -m nse_quant.cli.event_impact_mapping_cli map `
  --db .\data\warehouse.duckdb `
  --input .\payload.json `
  --enabled `
  --blackout-minutes-before 30 `
  --blackout-minutes-after 30
```

## Rules

- Missing required fields are rejected.
- Invalid timestamps are rejected.
- Mapper signature mismatch is rejected.
- Missing database or input file is rejected.
- Mapping is returned only when mapper returns a truthy result.
