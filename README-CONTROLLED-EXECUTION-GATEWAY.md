# Controlled execution gateway

Extract this archive at the repository root. It places:

- src/nse_quant/data_platform/native_controlled_execution_gateway.py
- tests/data_platform/test_native_controlled_execution_gateway.py
- README-CONTROLLED-EXECUTION-GATEWAY.md

This adds a narrowly scoped controlled execution gateway. It remains paper-only
by default. Live order placement requires an explicitly enabled configuration,
an admitted Gold decision candidate, and an explicit execution authorization
flag.

Run:

uv run pytest tests/data_platform/test_native_controlled_execution_gateway.py -x -q --tb=short
uv run pytest tests/data_platform -q
uv run ruff check src/nse_quant/data_platform tests/data_platform
uv run mypy
git diff --check

No eligibility grant, healing, backfill, adoption, or automatic execution.
POINT_IN_TIME_DECISION remains rejected. All seven native gates remain open;
package QA is not platform acceptance.
