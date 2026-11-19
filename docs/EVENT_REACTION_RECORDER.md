# Event-impact outcome reaction recorder

`src/nse_quant/research/event_reaction_recorder.py` is a pure additive persistence layer that records observed post-event market reactions, closing the gap between `event_impact_evidence` and `event_outcome_panel`.

## Contract

- `initialize_event_reactions(target)` creates the `event_reactions` table.
- `record_event_reaction(target, reaction)` persists one `EventReaction`; idempotent by `impact_id`.
- `read_event_reactions(reader, event_id=..., instrument=...)` is a read-only query with optional filters.
- `classify_reaction(reaction)` returns `ADVERSE_MOVE`, `IV_CRUSH`, `OBSERVED`, or `INSUFFICIENT_DATA`.

## Safety

- Research-only persistence; no decision gate, order, or eligibility change.
- `decision_eligibility_asserted=False` on every record, result, and classification.
- Idempotent by `impact_id`; re-recording the same impact returns `ALREADY_RECORDED` without duplicating rows.
- Reaction measures are nullable; missing measures classify as `INSUFFICIENT_DATA`, never as a fabricated outcome.
