# Event outcome research panel

`build_event_outcomes` joins retained `event_impact_evidence` with observed `event_reactions` to evaluate whether pre-event synthesis was useful.

## Contract

- Input: DuckDB connection and `EventOutcomePanelSettings`.
- Output: one outcome per matching event-impact and reaction pair.
- Classification: `ADVERSE_MOVE`, `IV_CRUSH`, `OBSERVED`, or `INSUFFICIENT_DATA`.
- Summary: outcome counts, recommended-action counts, and mean spot return.

## Safety

- Read-only research; no decision gate, order, or eligibility change.
- Missing reaction measures classify as `INSUFFICIENT_DATA`, never as a fabricated outcome.
- The panel does not modify `event_impact_evidence` or `event_reactions`.
