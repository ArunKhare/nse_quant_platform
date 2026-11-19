# Event reaction observation capture

`EventReactionRecorder` captures bounded post-event market reactions for affected instruments. It records research evidence; it does not interpret event truth, authorize execution, or create a decision gate.

## Contract

- Input: one event, instrument, configured observation window, baseline market state, and observed market state.
- Output: one `event_reactions` row with a deterministic reaction ID.
- Duplicate capture: idempotent through `INSERT OR REPLACE` on the deterministic reaction ID.
- Unconfigured window: rejected before persistence.

## Captured measures

- Spot return percentage.
- Realized range in points.
- ATM IV change.
- Expected-move change in points.
- PCR change.
- Relevant OI change.
- Option-spread change in percentage points.

Missing observed fields produce a null measure and mark the reaction incomplete; they never fabricate a value.

## Safety

- `enabled` defaults to `false`.
- No automatic order placement, modification, cancellation, or forced exit.
- No decision-eligibility grant.
- Reaction evidence is retained for later research and rule validation only.
