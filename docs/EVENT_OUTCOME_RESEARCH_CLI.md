# Event outcome research CLI

`event-outcome-research build` builds a bounded event outcome research panel for an instrument.

## Contract

- Input: reviewed JSON payload with event ID, instrument, observation window, baseline, and observed market state.
- Output: receipt with `BUILT` or `REJECTED` status and panel payload.
- Safety: never asserts event truth, never grants decision eligibility, never enables live trading.

## Usage

```powershell
uv run python -m nse_quant.cli.event_outcome_research_cli build `
  --input .\payload.json `
  --enabled `
  --observation-window-minutes 60 `
  --max-payload-bytes 65536
```

## Rules

- Missing required fields are rejected.
- Invalid window is rejected.
- Window out of bounds is rejected.
- Oversized payload is rejected.
- Baseline and observed must be objects.
- Spot return, IV change, expected move change, PCR change, OI change, and option spread change are computed when inputs are numeric.
