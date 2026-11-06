# Event impact synthesis CLI

`event-impact-synthesis synthesize` synthesizes bounded event impact evidence for an instrument.

## Contract

- Input: reviewed JSON payload with event ID, instrument, decision timestamp, mapping, and optional surprise.
- Output: receipt with `SYNTHESIZED` or `REJECTED` status and evidence payload.
- Safety: never asserts event truth, never grants decision eligibility, never enables live trading.

## Usage

```powershell
uv run python -m nse_quant.cli.event_impact_synthesis_cli synthesize `
  --input .\payload.json `
  --enabled `
  --block-new-entries `
  --max-payload-bytes 65536
```

## Rules

- Missing required fields are rejected.
- Invalid timestamps are rejected.
- Mapping must be an object.
- Payload size is bounded.
- Confidence outside 0..1 is retained as null.
- High volatility with block enabled produces `BLOCK_NEW_ENTRIES`; otherwise `OBSERVE`.
