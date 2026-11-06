# LLM enrichment link CLI

`llm-enrichment-link` links LLM enrichment metadata to a reviewed market event within a configured time window.

## Contract

- Input: reviewed JSON payload with enrichment ID, event ID, instrument, event timestamp, and observed timestamp.
- Output: receipt with `LINKED`, `DUPLICATE`, or `REJECTED` status.
- Safety: never asserts event truth, never grants decision eligibility, never enables live trading.

## Usage

```powershell
uv run python -m nse_quant.cli.llm_enrichment_link_cli link `
  --input .\payload.json `
  --enabled `
  --max-link-window-minutes 60
```

## Rules

- Missing required fields are rejected.
- Invalid timestamps are rejected.
- Missing or invalid input file is rejected.
- Link window is bounded by `max_link_window_minutes`.
- Both enrichment and event must already exist.
- Duplicate link ID returns `DUPLICATE` without rewriting.
