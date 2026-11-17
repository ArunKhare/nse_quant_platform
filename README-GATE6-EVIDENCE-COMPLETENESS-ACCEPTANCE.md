# Gate 6: evidence-completeness acceptance tests

Extract this archive at the repository root. It places:

- tests/data_platform/test_native_iron_condor_gate6_acceptance.py
- README-GATE6-EVIDENCE-COMPLETENESS-ACCEPTANCE.md

This upgrades the end-to-end Gate 6 acceptance tests to also validate that the
persisted reconciliation is evidence-complete: authoritative identity/time
evidence, coverage evidence-link context, and exact replay coverage for every
recorded stage.

Run:

uv run pytest tests/data_platform/test_native_iron_condor_gate6_acceptance.py -x -q --tb=short
uv run pytest tests/data_platform -q
uv run ruff check src/nse_quant/data_platform tests/data_platform
uv run mypy
git diff --check

No eligibility, live trading, healing, backfill, adoption, or execution
authority. POINT_IN_TIME_DECISION remains rejected. All seven native gates
remain open; package QA is not platform acceptance.
