# Complete exact replay of stages that actually run

`replay_stage` and `replay_stage_chain` re-derive the same outcome from the same inputs for stages that actually ran (strategy, portfolio_risk), extending the existing refusal decision's pre-strategy replay to cover the full stage chain.

## Contract

- Input: `StageRecord` (stage, inputs, outcome) and a callable evaluator; or a list of records plus a dict of evaluators.
- Output: `ReplayResult` (stage, replayed, outcome_matches, reason) or a list of them.
- Safety: never synthesizes outcomes, never grants decision eligibility, never enables live trading.

## Rules

- Replays only stages that actually ran (has an evaluator).
- Refuses missing evaluator, non-callable evaluator, evaluator errors.
- Addresses the "complete exact replay of stages that actually run" sub-gap of gate 6 from docs/CURRENT_NATIVE_STATUS.md.
