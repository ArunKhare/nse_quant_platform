# Gate 6: end-to-end native decision-run pipeline

Extract this archive at the repository root. It places:

- src/nse_quant/data_platform/native_iron_condor_decision_run_pipeline.py
- tests/data_platform/test_native_iron_condor_decision_run_pipeline.py
- README-GATE6-NATIVE-DECISION-RUN-PIPELINE.md

Requires the already-delivered native iron-condor decision-run orchestrator and
native iron-condor decision reconciliation persistence modules.

Run:

uv run pytest tests/data_platform/test_native_iron_condor_decision_run_pipeline.py -x -q --tb=short
uv run pytest tests/data_platform -q
uv run ruff check src/nse_quant/data_platform tests/data_platform
uv run mypy
git diff --check

No eligibility, live trading, healing, backfill, adoption, or execution
authority. POINT_IN_TIME_DECISION remains rejected. All seven native gates
remain open; package QA is not platform acceptance.
