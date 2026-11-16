# Native strategy input coverage

Source-reconciled input-coverage reconciliation for `iron_condor_monitor`.

- Module: `native_strategy_input_coverage.py`
- Inventory: `native_strategy_requirements.REQUIREMENTS`
- Statuses: `covered`, `missing`, `unlinked`
- `authoritative_identity_and_time` is never auto-coverable
- No healing, backfill, eligibility grant, or execution authority
- `decision_eligibility_asserted=False` always
