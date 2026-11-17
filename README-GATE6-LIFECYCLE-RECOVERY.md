# Gate 6: lifecycle recovery observations

Extract this archive at the repository root. It places:

- src/nse_quant/data_platform/native_decision_lifecycle_recovery.py
- tests/data_platform/test_native_decision_lifecycle_recovery.py
- README-GATE6-LIFECYCLE-RECOVERY.md

This adds narrowly scoped lifecycle-recovery observations for failed,
incomplete, unlinked, or orphan obligations. It records recovery attempts
without healing, mutating, adopting, or erasing the original obligation.

Run:

uv run pytest tests/data_platform/test_native_decision_lifecycle_recovery.py -x -q --tb=short
uv run pytest tests/data_platform -q
uv run ruff check src/nse_quant/data_platform tests/data_platform
uv run mypy
git diff --check

No eligibility, live trading, healing, backfill, adoption, or execution
authority. POINT_IN_TIME_DECISION remains rejected. All seven native gates
remain open; package QA is not platform acceptance.
