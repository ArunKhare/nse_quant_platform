# Native execution-stage refusal record

`execution_refusal_record` explicitly records the `execution` stage as `NOT_RUN` in a refusal decision.

## Contract

- Input: refusal decision dict with a `stages` dict.
- Output: updated refusal decision with `execution` stage added as `NOT_RUN`.
- Safety: never enables live trading, never grants eligibility, never bypasses the kill switch.

## Rules

- Refuses if `execution` stage already recorded.
- Refuses if `stages` missing or not a dict.
- Preserves all original stages unchanged.
