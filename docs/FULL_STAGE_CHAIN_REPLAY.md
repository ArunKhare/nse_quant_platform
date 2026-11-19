# Full stage-chain replay

`replay_full_stage_chain` replays the full 7-stage chain (kill_switch, safety_boundary, publication_admission, native_inputs, strategy, portfolio_risk, execution) in order, verifying the full chain.

## Contract

- Input: records (list of FullStageRecord covering all 7 stages in order), evaluators (dict of stage -> callable).
- Output: list of FullChainReplayResult (stage, replayed, outcome_matches, reason).
- Safety: never grants eligibility, never enables live trading.

## Rules

- Chain must cover all 7 stages in the exact order of FULL_STAGE_CHAIN.
- Refuses order mismatch, missing evaluator, evaluator error, non-list records, non-dict evaluators.
- Addresses the "full stage-chain replay" sub-gap of gate 6 from docs/CURRENT_NATIVE_STATUS.md.
