# Silver-backed native strategy input coverage

Read-only, Silver-backed coverage derivation for `iron_condor_monitor`.

- Mapped requirements now include `chain_time_expiry_spot`, `option_chain_and_contract_terms`, and `candidate_liquidity` via the native option-chain snapshot Silver.
- `authoritative_identity_and_time` remains explicitly unmapped and never auto-coverable.
- No eligibility, execution authority, or backfill.
- `decision_eligibility_asserted=False` always.
