# Gate 6: coverage evidence-link validation

Extract this archive at the repository root. It places:

- src/nse_quant/data_platform/native_strategy_coverage_evidence_links.py
- tests/data_platform/test_native_strategy_coverage_evidence_links.py
- README-GATE6-COVERAGE-EVIDENCE-LINKS.md

This adds narrowly scoped validation for coverage evidence links. Every covered
native requirement must have a well-formed Silver evidence link with exact
revision and recording-fingerprint pins.

Run:

uv run pytest tests/data_platform/test_native_strategy_coverage_evidence_links.py -x -q --tb=short
uv run pytest tests/data_platform -q
uv run ruff check src/nse_quant/data_platform tests/data_platform
uv run mypy
git diff --check

No eligibility, live trading, healing, backfill, adoption, or execution
authority. POINT_IN_TIME_DECISION remains rejected. All seven native gates
remain open; package QA is not platform acceptance.
