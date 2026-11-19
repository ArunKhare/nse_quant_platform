# Institutional regime skew component

`compute_skew` computes point-in-time put/call IV skew from a chain snapshot for the institutional regime plugin.

## Contract

- Input: put IV, call IV, and `InstitutionalRegimeSkewSettings`.
- Output: skew state, skew value, and threshold.
- Safety: never asserts market truth, never grants decision eligibility, never enables live trading.

## Rules

- Missing IV inputs return unavailable.
- Invalid IV inputs return unavailable.
- Skew above threshold classifies as HIGH_PUT_SKEW.
- Skew below negative threshold classifies as HIGH_CALL_SKEW.
- Otherwise classifies as NORMAL_SKEW.
