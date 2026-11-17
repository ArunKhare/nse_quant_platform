# Native authority evidence ingestion

Extract this archive at the repository root. It places:

- src/nse_quant/data_platform/native_authority_evidence_ingestion.py
- tests/data_platform/test_native_authority_evidence_ingestion.py
- README-NATIVE-AUTHORITY-EVIDENCE-INGESTION.md

This adds narrowly scoped ingestion for independently sourced identity/time,
availability, and economic-validity evidence from an accepted authority. It
records original first-write, audit, orphan-check, and final-audit obligations
without healing original failed, incomplete, unlinked, or orphan obligations.

Run:

uv run pytest tests/data_platform/test_native_authority_evidence_ingestion.py -x -q --tb=short
uv run pytest tests/data_platform -q
uv run ruff check src/nse_quant/data_platform tests/data_platform
uv run mypy
git diff --check

No eligibility grant, live trading, healing, backfill, adoption, or execution
authority. POINT_IN_TIME_DECISION remains rejected. All seven native gates
remain open; package QA is not platform acceptance.
