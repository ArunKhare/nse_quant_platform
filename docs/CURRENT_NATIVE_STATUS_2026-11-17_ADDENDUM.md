## 2026-11-17 addendum: native decision-run implementation

Status reconciliation: 2026-11-17. This addendum records recently implemented
native decision-run capability and reconciles it with the current gate status.
It does not close any native gate, grant decision eligibility, authorize live
trading, or interpret package QA as platform acceptance.

### Native option-chain snapshot

User QA passed for native option-chain snapshot Bronze and Silver.

- Native option-chain snapshot Bronze and Silver are accepted user QA.
- Silver-backed native strategy input coverage now maps:
  - `chain_time_expiry_spot`
  - `option_chain_and_contract_terms`
  - `candidate_liquidity`
- Together with the previously mapped `market_session`,
  `iv_rank_and_history`, `iv_rv_spread`, `expected_move`, and
  `effective_proposal_configuration`, eight non-identity requirements are now
  mapped.
- `authoritative_identity_and_time` remains explicitly unmapped and is never
  auto-coverable.
- No eligibility, execution authority, backfill, or healing is asserted.

### Actual audited native decisions


Every successful result retains `decision_eligibility_asserted=False`.
`POINT_IN_TIME_DECISION` remains rejected before recording or replay. A stage
not recorded for a run remains explicitly `STAGE_NOT_EXECUTED`; it is never
fabricated, inferred, or healed.

### Decision-run coverage reconciliation

Implemented and pending user QA:


The reconciliation preserves exact `covered`, `unlinked`, `missing`, and
`evidence_refs` collections. It does not map an uncovered requirement, backfill
evidence, heal an obligation, or assert completion. `complete=True` is not
assertable by the reconciliation store while `authoritative_identity_and_time`
remains unmapped.

### Gate status

Gate 6 remains open. Its implemented portions now include actual audited
native strategy/risk decisions, evidence-linked coverage reconciliation, and
exact replay of stages that actually ran. Gate 6 still requires complete
required native inputs, including the unresolved authoritative identity and
time boundary.

All seven native gates remain open. Package QA is not platform acceptance.
Data loading/migration, live acquisition, user-data migration or backfill,
real identity/key/policy/authority registration, production publication,
trading, and decision-loop cutover remain unauthorized.

### Later native-platform increments

The following later native-platform increments are implemented and
user-QA-confirmed. They remain observational and do not close any native status
gate, grant decision eligibility, authorize live trading, or authorize healing,
backfill, adoption, or execution.

- Availability and economic-validity evidence validation.
- Gold decision publication candidate validation.
- Eligible admission contract evaluation.
- Lifecycle-recovery observations.
- Operational acceptance harness.
- Controlled execution gateway with paper-only default behavior.
- Multi-underlying expansion validation for NIFTY and BANKNIFTY.
- Native authority-evidence completeness-report audit-trail import, round-trip, acceptance, and reconciliation governance.
- Native authority-evidence completeness-report audit-trail end-to-end lifecycle acceptance.


`POINT_IN_TIME_DECISION` remains rejected before recording, replay, publication,
admission, or execution. The controlled execution gateway remains paper-only by
default; live placement requires explicit configuration, an admitted Gold
decision candidate, and explicit user authorization. Multi-underlying expansion
validation supports NIFTY and BANKNIFTY canonical underlying support and
derivative binding only.

### Native authority evidence completeness report audit-trail persistence and replay

Implemented native persistence and exact replay for enforced audit trails
covering identity/time, availability, and economic-validity evidence.

- Persists enforced audit trails only after enforcement completion.
- Validates a valid 64-character enforcement fingerprint and exact canonical
  SHA-256 match.
- Preserves exact missing obligations for original_first_write, audit,
  orphan_check, and final_audit.
- Integrates audit, orphan-check, and final-audit context only when the
  corresponding obligation is present.
- Preserves the full lifecycle from retained through persisted.
- Produces a deterministic SHA-256 persistence fingerprint.
- Replays exactly and independently verifies both persistence and enforcement
  fingerprints.
- Rejects invalid or mismatched fingerprints, healing, incomplete enforcement
  or persistence, and POINT_IN_TIME_DECISION.
- Returns decision_eligibility_asserted=False; no eligibility, live trading,
  healing, backfill, adoption, or execution authority is granted.
- All seven native gates remain open; package QA is not platform acceptance.

## Authority evidence audit-trail enforcement and persistence replay

The following native authority-evidence completeness-report audit-trail
increments are implemented and user-QA-confirmed. They remain observational and
do not close any native status gate, grant decision eligibility, authorize live
trading, or authorize healing, backfill, adoption, or execution.

- Native authority-evidence completeness-report audit-trail enforcement:
  enforces the governed lifecycle of retained audit trails across identity/time,
  availability, and economic-validity evidence.
- Native authority-evidence completeness-report audit-trail persistence and
  replay: persists enforced audit trails and replays them exactly while
  independently verifying both persistence and enforcement fingerprints.

Enforcement requires a valid 64-character governance fingerprint and an exact
canonical SHA-256 match. It reports exact missing obligations for
`original_first_write`, `audit`, `orphan_check`, and `final_audit`; integrates
audit, orphan-check, and final-audit context only when the corresponding
obligation is present; includes the lifecycle from `retained` through
`persisted`; and computes a deterministic SHA-256 enforcement fingerprint.

Persistence requires enforcement completion and an exact enforcement
fingerprint. It preserves missing obligations without healing, computes a
deterministic persistence fingerprint, and replay independently verifies both
persistence and enforcement fingerprints.

`POINT_IN_TIME_DECISION`, invalid or mismatched fingerprints, and healing remain
rejected. `decision_eligibility_asserted` remains `False`. Original failed,
incomplete, unlinked, or orphan obligations are not healed by later success.

## Authority evidence audit-trail import and reconciliation

The native authority-evidence completeness-report audit-trail import, round-trip,
acceptance, and reconciliation governance increment is implemented and
user-QA-confirmed. It imports exported audit trails exactly, performs
non-destructive round-trip replay, governs acceptance, and reconciles audit
trails across identity/time, availability, and economic-validity evidence.

It validates the completed query-and-export result and requires valid
64-character query-export, query, archival-governance, retention-governance,
persistence, and enforcement fingerprints with exact canonical SHA-256 matches.
It preserves exact missing obligations, integrates audit, orphan-check, and
final-audit context only when present, and includes the lifecycle from
`retained` through `imported`, `round_tripped`, and `accepted`.

It produces distinct `imported`, `round_tripped`, `accepted`, and `reconciled`
result keys referencing the same immutable governed envelope and computes a
deterministic SHA-256 governance fingerprint. Replay independently verifies the
governance fingerprint.

`POINT_IN_TIME_DECISION`, invalid or mismatched fingerprints, healing, and
deletion remain rejected. `decision_eligibility_asserted` remains `False`.
Original failed, incomplete, unlinked, or orphan obligations are not healed by
later success.