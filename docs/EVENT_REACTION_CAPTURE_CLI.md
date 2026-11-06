# Event reaction capture CLI

`event-reaction-capture capture` captures a bounded post-event market reaction using the event reaction recorder.

## Contract

- Input: reviewed JSON payload with event, instrument, observation window, baseline, and observed market state.
- Output: receipt with `CAPTURED` or `REJECTED` status and reaction payload.
- Safety: never asserts event truth, never grants decision eligibility, never enables live trading.

## Usage

```powershell
uv run python -m nse_quant.cli.event_reaction_capture_cli capture `
  --db .\data\warehouse.duckdb `
  --input .\payload.json
```

## Rules

- Missing required fields are rejected.
- Recorder signature mismatch is rejected.
- Missing database or input file is rejected.
- Reaction is captured only when recorder returns a truthy result.
