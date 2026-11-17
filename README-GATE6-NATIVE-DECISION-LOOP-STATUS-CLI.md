# Gate 6: native decision-loop status/query CLI

Extract this archive at the repository root. It places:

- src/nse_quant/data_platform/native_iron_condor_decision_loop_status_cli.py
- tests/data_platform/test_native_iron_condor_decision_loop_status_cli.py
- README-GATE6-NATIVE-DECISION-LOOP-STATUS-CLI.md

This exposes a read-only status/query CLI for persisted native decision
reconciliations. It inspects and exactly replays a reconciliation with
authoritative identity/time evidence, printing a JSON observational result.

Run:

uv run pytest tests/data_platform/test_native_iron_condor_decision_loop_status_cli.py -x -q --tb=short
uv run pytest tests/data_platform -q
uv run ruff check src/nse_quant/data_platform tests/data_platform
uv run mypy
git diff --check

No eligibility, live trading, healing, backfill, adoption, or execution
authority. POINT_IN_TIME_DECISION remains rejected. All seven native gates
remain open; package QA is not platform acceptance.
