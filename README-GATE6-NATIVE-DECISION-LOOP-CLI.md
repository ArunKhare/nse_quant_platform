# Gate 6: native decision-loop CLI

Extract this archive at the repository root. It places:

- src/nse_quant/data_platform/native_iron_condor_decision_loop_cli.py
- tests/data_platform/test_native_iron_condor_decision_loop_cli.py
- README-GATE6-NATIVE-DECISION-LOOP-CLI.md

This exposes the existing read-only decision-loop integration through a
narrowly scoped CLI. It reads JSON request, coverage, and authoritative boundary
documents; runs, reconciles, persists, and replays the decision run; and prints
a JSON observational result.

Run:

uv run pytest tests/data_platform/test_native_iron_condor_decision_loop_cli.py -x -q --tb=short
uv run pytest tests/data_platform -q
uv run ruff check src/nse_quant/data_platform tests/data_platform
uv run mypy
git diff --check

No eligibility, live trading, healing, backfill, adoption, or execution
authority. POINT_IN_TIME_DECISION remains rejected. All seven native gates
remain open; package QA is not platform acceptance.
