# Gate 6: composite audited decision-run recording and replay

Extract this archive at the repository root. It places:

- src/nse_quant/data_platform/audited_decision_run_composite.py
- tests/data_platform/test_audited_decision_run_composite.py
- README-GATE6-COMPOSITE-AUDITED-DECISION-RUN.md

Requires the already-delivered and QA-passed:

- src/nse_quant/data_platform/audited_decision_run.py
- src/nse_quant/data_platform/audited_decision_run_silver.py
- tests/data_platform/test_audited_decision_run_silver.py

Run:

uv run pytest tests/data_platform/test_audited_decision_run_composite.py -x -q --tb=short
uv run pytest tests/data_platform -q
uv run ruff check src/nse_quant/data_platform tests/data_platform
uv run mypy
git diff --check

No eligibility, live trading, healing, backfill, adoption, or execution
authority. POINT_IN_TIME_DECISION remains rejected. All seven native gates
remain open; package QA is not platform acceptance.
