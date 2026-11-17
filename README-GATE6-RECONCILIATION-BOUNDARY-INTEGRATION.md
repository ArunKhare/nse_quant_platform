# Gate 6: reconciliation boundary integration

Extract this archive at the repository root. It places:

- src/nse_quant/data_platform/native_iron_condor_decision_reconciliation_boundary.py
- tests/data_platform/test_native_iron_condor_decision_reconciliation_boundary.py
- README-GATE6-RECONCILIATION-BOUNDARY-INTEGRATION.md

This integrates the authoritative identity/time boundary into the persisted
reconciliation document. It validates the boundary, embeds its exact context,
persists the extended reconciliation, and replays it exactly.

Run:

uv run pytest tests/data_platform/test_native_iron_condor_decision_reconciliation_boundary.py -x -q --tb=short
uv run pytest tests/data_platform -q
uv run ruff check src/nse_quant/data_platform tests/data_platform
uv run mypy
git diff --check

No eligibility, live trading, healing, backfill, adoption, or execution
authority. POINT_IN_TIME_DECISION remains rejected. All seven native gates
remain open; package QA is not platform acceptance.
