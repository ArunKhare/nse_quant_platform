# Event outcome research validation archive CLI

`event-outcome-research-validation-archive archive` archives persisted event outcome research evidence to JSONL.

## Contract

- Input: reviewed JSON payload with event ID and instrument.
- Output: JSONL file with archived records.
- Receipt: `ARCHIVED` or `REJECTED` status and archived count.
- Safety: never asserts event truth, never grants decision eligibility, never enables live trading.

## Usage

```powershell
uv run python -m nse_quant.cli.event_outcome_research_validation_archive_cli archive `
  --db .\data\warehouse.duckdb `
  --input .\payload.json `
  --output .rchive.jsonl `
  --enabled `
  --max-records 100
```

## Rules

- Missing required fields are rejected.
- Query is bounded by max records.
- Records are ordered by persisted_at descending.
- Archive is bounded by max records.
