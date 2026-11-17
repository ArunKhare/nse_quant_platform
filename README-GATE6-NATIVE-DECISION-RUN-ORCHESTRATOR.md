# Gate 6: native iron-condor decision-run orchestrator

Extract this archive at the repository root. It places:

- src/nse_quant/data_platform/native_iron_condor_decision_run_orchestrator.py
- tests/data_platform/test_native_iron_condor_decision_run_orchestrator.py
- README-GATE6-NATIVE-DECISION-RUN-ORCHESTRATOR.md

Requires the already-delivered native strategy and portfolio-risk evaluators,
composite audited decision-run recorder, and Silver-backed coverage modules.

Run:

uv run pytest tests/data_platform/test_native_iron_condor_decision_run_orchestrator.py -x -q --tb=short
uv run pytest tests/data_platform -q
uv run ruff check src/nse_quant/data_platform tests/data_platform
uv run mypy
git diff --check

No eligibility, live trading, healing, backfill, adoption, or execution
authority. POINT_IN_TIME_DECISION remains rejected. All seven native gates
remain open; package QA is not platform acceptance.
