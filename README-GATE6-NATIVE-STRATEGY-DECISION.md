# Gate 6: native iron-condor strategy decision evaluation

Extract this archive at the repository root. It places:

- src/nse_quant/data_platform/native_iron_condor_strategy_decision.py
- tests/data_platform/test_native_iron_condor_strategy_decision.py
- README-GATE6-NATIVE-STRATEGY-DECISION.md

Requires the existing Silver-backed native strategy input coverage modules.

Run:

uv run pytest tests/data_platform/test_native_iron_condor_strategy_decision.py -x -q --tb=short
uv run pytest tests/data_platform -q
uv run ruff check src/nse_quant/data_platform tests/data_platform
uv run mypy
git diff --check

No eligibility, live trading, healing, backfill, adoption, or execution
authority. POINT_IN_TIME_DECISION remains rejected. All seven native gates
remain open; package QA is not platform acceptance.
