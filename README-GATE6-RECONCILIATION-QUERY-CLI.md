# Gate 6: bounded reconciliation query CLI

Extract this archive at the repository root. It places:

- src/nse_quant/data_platform/native_iron_condor_decision_reconciliation_query.py
- tests/data_platform/test_native_iron_condor_decision_reconciliation_query.py
- README-GATE6-RECONCILIATION-QUERY-CLI.md

This adds a bounded, read-only query for persisted native decision
reconciliations. It returns reconciliation summaries only; it does not heal,
backfill, adopt, grant eligibility, or execute anything.

Run:

uv run pytest tests/data_platform/test_native_iron_condor_decision_reconciliation_query.py -x -q --tb=short
uv run pytest tests/data_platform -q
uv run ruff check src/nse_quant/data_platform tests/data_platform
uv run mypy
git diff --check

No eligibility, live trading, healing, backfill, adoption, or execution
authority. POINT_IN_TIME_DECISION remains rejected. All seven native gates
remain open; package QA is not platform acceptance.
