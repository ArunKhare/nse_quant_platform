# Gate 6: persisted audited decision-run reconciliation Silver

Extract this archive at the repository root. It places:

- src/nse_quant/data_platform/audited_decision_reconciliation_silver.py
- tests/data_platform/test_audited_decision_reconciliation_silver.py
- README-GATE6-RECONCILIATION-SILVER.md

Requires the existing audit ledger, contracts, native strategy requirements,
and native strategy input coverage modules.

Run:

uv run pytest tests/data_platform/test_audited_decision_reconciliation_silver.py -x -q --tb=short
uv run pytest tests/data_platform -q
uv run ruff check src/nse_quant/data_platform tests/data_platform
uv run mypy
git diff --check

No eligibility, live trading, healing, backfill, adoption, or execution
authority. POINT_IN_TIME_DECISION remains rejected. All seven native gates
remain open; package QA is not platform acceptance.
