# Gate 6: end-to-end acceptance tests

Extract this archive at the repository root. It places:

- tests/data_platform/test_native_iron_condor_gate6_acceptance.py
- README-GATE6-END-TO-END-ACCEPTANCE.md

This adds end-to-end Gate 6 acceptance tests that exercise the full library
path: native decision-run recording, coverage evidence-link validation,
authoritative identity/time boundary validation, reconciliation persistence,
exact replay, duplicate rejection, and POINT_IN_TIME_DECISION rejection.

Run:

uv run pytest tests/data_platform/test_native_iron_condor_gate6_acceptance.py -x -q --tb=short
uv run pytest tests/data_platform -q
uv run ruff check src/nse_quant/data_platform tests/data_platform
uv run mypy
git diff --check

No eligibility, live trading, healing, backfill, adoption, or execution
authority. POINT_IN_TIME_DECISION remains rejected. All seven native gates
remain open; package QA is not platform acceptance.
