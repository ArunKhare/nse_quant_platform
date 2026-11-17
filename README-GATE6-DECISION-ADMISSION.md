# Gate 6: eligible publication/admission contract

Extract this archive at the repository root. It places:

- src/nse_quant/data_platform/native_iron_condor_decision_admission.py
- tests/data_platform/test_native_iron_condor_decision_admission.py
- README-GATE6-DECISION-ADMISSION.md

This adds a narrowly scoped admission contract that evaluates a versioned Gold
decision candidate against required evidence completeness. It returns an
admission determination but does not grant blanket eligibility, authorize live
trading, healing, backfill, adoption, or execution.

Run:

uv run pytest tests/data_platform/test_native_iron_condor_decision_admission.py -x -q --tb=short
uv run pytest tests/data_platform -q
uv run ruff check src/nse_quant/data_platform tests/data_platform
uv run mypy
git diff --check

POINT_IN_TIME_DECISION remains rejected. All seven native gates remain open;
package QA is not platform acceptance.
