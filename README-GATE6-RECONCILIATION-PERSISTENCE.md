# Gate 6: native decision-run reconciliation persistence

Extract this archive at the repository root. It places:

- src/nse_quant/data_platform/native_iron_condor_decision_reconciliation_persistence.py
- tests/data_platform/test_native_iron_condor_decision_reconciliation_persistence.py
- README-GATE6-RECONCILIATION-PERSISTENCE.md

Requires the already-delivered native iron-condor decision-run reconciliation
and persisted audited decision reconciliation Silver modules.

Run:

uv run pytest tests/data_platform/test_native_iron_condor_decision_reconciliation_persistence.py -x -q --tb=short
uv run pytest tests/data_platform -q
uv run ruff check src/nse_quant/data_platform tests/data_platform
uv run mypy
git diff --check

No eligibility, live trading, healing, backfill, adoption, or execution
authority. POINT_IN_TIME_DECISION remains rejected. All seven native gates
remain open; package QA is not platform acceptance.
