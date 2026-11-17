# Native decision-run coverage reconciliation

`reconcile_audited_decision_run` links a recorded and replayed composite audited
decision run to the current Silver-backed native strategy input coverage report.

This is observational only. It never grants eligibility, enables live trading,
heals a coverage gap, backfills evidence, or authorizes execution.

## Contract

- Input: current Silver-backed coverage report, run ID, requested stages, and
  per-stage revision/recording-fingerprint pins.
- Output: reconciliation document with exact coverage partitions, evidence
  references, stage replay status, completion status, and
  `decision_eligibility_asserted=False`.
- Safety: `POINT_IN_TIME_DECISION` remains rejected; no eligibility or
  execution authority is asserted.

## Rules

- Coverage report identity must match the native requirement inventory.
- `covered`, `unlinked`, `missing`, and `evidence_refs` are preserved exactly.
- `authoritative_identity_and_time` is never auto-coverable.
- A requested stage without a revision/recording pin is `STAGE_NOT_EXECUTED`.
- A stage is replayed only when its stored revision and recording fingerprint
  match exactly.
- `complete` is true only when the coverage report is complete and every
  requested stage was replayed.
- The persisted reconciliation Silver records an immutable reconciliation and
  supports exact replay of that reconciliation.

## Gate 6 scope

This addresses the reconciliation portion of Gate 6. It does not close Gate 6:
`authoritative_identity_and_time` remains unmapped, and all seven native gates
remain open. Package QA is not platform acceptance.
