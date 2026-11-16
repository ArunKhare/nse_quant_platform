# Evidence-linked native strategy input coverage

Derives `iron_condor_monitor` input coverage from explicit pinned Silver evidence.

- Module: `native_strategy_input_coverage_evidence.py`
- Inventory: `native_strategy_requirements.REQUIREMENTS`
- Evidence pin: `requirement_id`, 64-hex `revision_id`, 64-hex `recording_fingerprint`, positive `row_count`
- Statuses: `covered` only with a valid pin; otherwise `missing`
- `authoritative_identity_and_time` is never auto-coverable
- No healing, backfill, eligibility grant, or execution authority
- `decision_eligibility_asserted=False` always
