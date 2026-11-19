# Exact replay of the full decision loop

`replay_full_decision_loop` combines full stage-chain replay, audited decision record, and strategy evaluation integration into a single replayable record.

## Contract

- Input: `FullLoopRequest` (gates, analytics, portfolio_risk, evaluators).
- Output: `FullLoopReplayRecord` with integrated, audited, replayed, replayable, reason, decision_eligibility_asserted (always False).
- Safety: never grants eligibility, never enables live trading.

## Rules

- Replayable only when audited.recorded and all replayed outcomes match.
- Strategy replay includes gates, analytics, and portfolio risk; malformed stage inputs are refused before audit or replay.
- Refuses invalid request.
- Addresses the "exact replay of the full decision loop" sub-gap of gate 6 from docs/CURRENT_NATIVE_STATUS.md.
