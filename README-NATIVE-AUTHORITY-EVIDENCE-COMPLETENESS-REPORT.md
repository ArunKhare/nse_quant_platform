# Native authority evidence completeness report and audit integration

Extract this archive at the repository root. It places:

- src/nse_quant/data_platform/native_authority_evidence_completeness_report.py
- tests/data_platform/test_native_authority_evidence_completeness_report.py
- README-NATIVE-AUTHORITY-EVIDENCE-COMPLETENESS-REPORT.md

This adds narrowly scoped completeness reporting for identity/time, availability,
and economic-validity evidence with exact audit, orphan-check, and final-audit
integration. It does not heal original failed, incomplete, unlinked, or orphan
obligations.

Run:

uv run pytest tests/data_platform/test_native_authority_evidence_completeness_report.py -x -q --tb=short
uv run pytest tests/data_platform -q
uv run ruff check src/nse_quant/data_platform tests/data_platform
uv run mypy
git diff --check

No eligibility grant, live trading, healing, backfill, adoption, or execution
authority. POINT_IN_TIME_DECISION remains rejected. All seven native gates
remain open; package QA is not platform acceptance.
