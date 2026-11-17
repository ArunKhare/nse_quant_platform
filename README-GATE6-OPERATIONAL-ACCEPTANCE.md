# Gate 6: integrated operational acceptance harness

Extract this archive at the repository root. It places:

- src/nse_quant/data_platform/native_iron_condor_operational_acceptance.py
- tests/data_platform/test_native_iron_condor_operational_acceptance.py
- README-GATE6-OPERATIONAL-ACCEPTANCE.md

This adds a bounded, multi-day operational acceptance harness for native
iron-condor decisions. It runs the full library path across complete trading
days: decision-run recording, coverage evidence-link validation, authoritative
identity/time validation, reconciliation persistence, evidence-completeness
validation, admission evaluation, and exact replay.

Run:

uv run pytest tests/data_platform/test_native_iron_condor_operational_acceptance.py -x -q --tb=short
uv run pytest tests/data_platform -q
uv run ruff check src/nse_quant/data_platform tests/data_platform
uv run mypy
git diff --check

No eligibility, live trading, healing, backfill, adoption, or execution
authority. POINT_IN_TIME_DECISION remains rejected. All seven native gates
remain open; package QA is not platform acceptance.
