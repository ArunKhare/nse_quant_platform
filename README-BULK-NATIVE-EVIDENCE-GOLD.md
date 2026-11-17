# Bulk implementation: native evidence and Gold publication candidate

Extract this archive at the repository root. It places:

- src/nse_quant/data_platform/native_authoritative_identity_time_evidence.py
- tests/data_platform/test_native_authoritative_identity_time_evidence.py
- src/nse_quant/data_platform/native_availability_economic_validity_evidence.py
- tests/data_platform/test_native_availability_economic_validity_evidence.py
- src/nse_quant/data_platform/native_iron_condor_decision_gold.py
- tests/data_platform/test_native_iron_condor_decision_gold.py
- README-BULK-NATIVE-EVIDENCE-GOLD.md

This implements the prioritized P0-P2 sequence:

1. Authoritative identity/time evidence Silver recording and exact replay.
2. Availability and economic-validity evidence Silver recording and exact replay,
   with separate `knowledge_cutoff` and `economic_at` axes.
3. Versioned Gold decision publication candidate and exact replay.

All modules are observational. No eligibility, live trading, healing, backfill,
adoption, or execution authority. `POINT_IN_TIME_DECISION` remains rejected.
All seven native gates remain open; package QA is not platform acceptance.

Run:

uv run pytest tests/data_platform/test_native_authoritative_identity_time_evidence.py tests/data_platform/test_native_availability_economic_validity_evidence.py tests/data_platform/test_native_iron_condor_decision_gold.py -x -q --tb=short
uv run pytest tests/data_platform -q
uv run ruff check src/nse_quant/data_platform tests/data_platform
uv run mypy
git diff --check
