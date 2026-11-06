# Event outcome panel CLI

`event-outcome-panel build` builds a bounded event outcome research panel from captured event reactions.

## Contract

- Input: event ID, instrument, and panel settings.
- Output: panel with row count, complete count, and rows.
- Safety: never asserts event truth, never grants decision eligibility, never enables live trading.

## Usage

```powershell
uv run python -m nse_quant.cli.event_outcome_panel_cli build `
  --db .\data\warehouse.duckdb `
  --event-id event-1 `
  --instrument NIFTY `
  --enabled `
  --max-rows 1000
```

## Rules

- Disabled panel build rejects with `event_outcome_panel_disabled`.
- Missing database is rejected.
- Only rows matching event ID and instrument are included.
- Rows are ordered by captured time and bounded by max rows.
- Complete count counts rows with `complete` true.
