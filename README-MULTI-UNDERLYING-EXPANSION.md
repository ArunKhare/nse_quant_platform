# Multi-underlying expansion validation

Extract this archive at the repository root. It places:

- src/nse_quant/data_platform/native_multi_underlying_expansion.py
- tests/data_platform/test_native_multi_underlying_expansion.py
- README-MULTI-UNDERLYING-EXPANSION.md

This adds narrowly scoped validation for canonical underlying support and
derivative binding across NIFTY and BANKNIFTY. It is observational only and
does not grant eligibility, live trading, healing, backfill, adoption, or
execution authority.

Run:

uv run pytest tests/data_platform/test_native_multi_underlying_expansion.py -x -q --tb=short
uv run pytest tests/data_platform -q
uv run ruff check src/nse_quant/data_platform tests/data_platform
uv run mypy
git diff --check

POINT_IN_TIME_DECISION remains rejected. All seven native gates remain open;
package QA is not platform acceptance.
