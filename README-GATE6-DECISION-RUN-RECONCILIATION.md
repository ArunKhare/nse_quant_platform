# Gate 6: audited decision-run coverage reconciliation

Extract this archive at the repository root. It places:

- src/nse_quant/data_platform/audited_decision_reconciliation.py
- tests/data_platform/test_audited_decision_reconciliation.py
- README-GATE6-DECISION-RUN-RECONCILIATION.md

Requires the already-delivered native strategy requirements and Silver-backed
coverage modules.

Run:

uv run pytest tests/data_platform/test_audited_decision_reconciliation.py -x -q --tb=short
uv run pytest tests/data_platform -q
uv run ruff check src/nse_quant/data_platform tests/data_platform
uv run mypy
git diff --check

No eligibility, live trading, healing, backfill, adoption, or execution
authority. POINT_IN_TIME_DECISION remains rejected. All seven native gates
remain open; package QA is not platform acceptance.
