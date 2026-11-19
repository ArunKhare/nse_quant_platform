# Event impact synthesis validation CLI

`event-impact-synthesis-validation validate` validates a bounded event impact synthesis against observed outcome.

## Contract

- Input: reviewed JSON payload with synthesis ID, event ID, instrument, decision timestamp, evidence, and outcome.
- Output: receipt with `VALIDATED` or `REJECTED` status and validation payload.
- Safety: never asserts event truth, never grants decision eligibility, never enables live trading.

## Usage

```powershell
uv run python -m nse_quant.cli.event_impact_synthesis_validation_cli validate `
  --input .\payload.json `
  --enabled `
  --max-payload-bytes 65536
```

## Rules

- Missing required fields are rejected.
- Oversized payload is rejected.
- Evidence and outcome must be objects.
- Timestamp must be valid ISO format.
- Validation is useful when high volatility aligns with large move, or low volatility aligns with small move.
