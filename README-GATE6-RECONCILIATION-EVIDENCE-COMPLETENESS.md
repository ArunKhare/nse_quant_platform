# Gate 6: reconciliation evidence completeness

Extract this archive at the repository root. It places:

- src/nse_quant/data_platform/native_iron_condor_reconciliation_evidence_completeness.py
- tests/data_platform/test_native_iron_condor_reconciliation_evidence_completeness.py
- README-GATE6-RECONCILIATION-EVIDENCE-COMPLETENESS.md

This adds narrowly scoped validation that a persisted reconciliation carries
authoritative identity/time evidence, coverage evidence-link context, and exact
replay coverage for every recorded stage.

Run:

uv run pytest tests/data_platform/test_native_iron_condor_reconciliation_evidence_completeness.py -x -q --tb=short
uv run pytest tests/data_platform -q
uv run ruff check src/nse_quant/data_platform tests/data_platform
uv run mypy
git diff --check

No eligibility, live trading, healing, backfill, adoption, or execution
authority. POINT_IN_TIME_DECISION remains rejected. All seven native gates
remain open; package QA is not platform acceptance.
