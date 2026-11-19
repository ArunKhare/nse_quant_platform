# Gate 6: persisted audited decision-run Silver

Extract this archive at the repository root. It places:

- src/nse_quant/data_platform/audited_decision_run_silver.py
- tests/data_platform/test_audited_decision_run_silver.py
- README-GATE6-AUDITED-DECISION-RUN.md

Requires the existing audited_decision_run.py module with
ensure_no_point_in_time_decision and bind_decision_run_to_coverage.

Run:

uv run pytest tests/data_platform/test_audited_decision_run_silver.py -x -q --tb=short
uv run pytest tests/data_platform -q
uv run ruff check src/nse_quant/data_platform tests/data_platform
uv run mypy
git diff --check

No eligibility, live trading, healing, backfill, adoption, or execution
authority. POINT_IN_TIME_DECISION remains rejected. All seven native gates
remain open; package QA is not platform acceptance.
