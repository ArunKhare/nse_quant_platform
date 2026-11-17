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

Implemented and pending user QA:

- `src/nse_quant/data_platform/audited_decision_record.py`: deterministic
  audited strategy or portfolio-risk decision fingerprints.
- `src/nse_quant/data_platform/audited_decision_run.py`: evidence-linked
  decision-run binding and explicit `POINT_IN_TIME_DECISION` rejection.
- `src/nse_quant/data_platform/audited_decision_run_silver.py`: persisted
  append-only per-stage audited decision-run Silver and exact stage replay.
- `src/nse_quant/data_platform/audited_decision_run_composite.py`: composite
  strategy and portfolio-risk run recording and exact replay.
- `src/nse_quant/data_platform/native_iron_condor_strategy_decision.py`:
  observational native strategy-stage evaluation from covered inputs.
- `src/nse_quant/data_platform/native_iron_condor_portfolio_risk_decision.py`:
  observational native portfolio-risk-stage evaluation.
- `src/nse_quant/data_platform/native_iron_condor_decision_run_orchestrator.py`:
  two-stage evaluation, composite recording, and exact replay.

Every successful result retains `decision_eligibility_asserted=False`.
`POINT_IN_TIME_DECISION` remains rejected before recording or replay. A stage
not recorded for a run remains explicitly `STAGE_NOT_EXECUTED`; it is never
fabricated, inferred, or healed.

### Decision-run coverage reconciliation

Implemented and pending user QA:

- `src/nse_quant/data_platform/audited_decision_reconciliation.py`: in-memory
  reconciliation of a decision run with the current Silver-backed coverage
  report.
- `src/nse_quant/data_platform/audited_decision_reconciliation_silver.py`:
  persisted append-only reconciliation Silver and exact reconciliation replay.

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
