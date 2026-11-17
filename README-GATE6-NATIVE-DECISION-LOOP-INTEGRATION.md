# Gate 6: native decision-loop integration

Extract this archive at the repository root. It places:

- src/nse_quant/data_platform/native_iron_condor_decision_loop_integration.py
- tests/data_platform/test_native_iron_condor_decision_loop_integration.py
- README-GATE6-NATIVE-DECISION-LOOP-INTEGRATION.md

This is the next narrowly scoped Gate 6 increment after reconciliation boundary
integration. It exposes one read-only decision-loop entry point that runs the
native pipeline, reconciles against current coverage with authoritative
identity/time evidence, persists that reconciliation, and exactly replays it.

Run:

uv run pytest tests/data_platform/test_native_iron_condor_decision_loop_integration.py -x -q --tb=short
uv run pytest tests/data_platform -q
uv run ruff check src/nse_quant/data_platform tests/data_platform
uv run mypy
git diff --check

No eligibility, live trading, healing, backfill, adoption, or execution
authority. POINT_IN_TIME_DECISION remains rejected. All seven native gates
remain open; package QA is not platform acceptance.
