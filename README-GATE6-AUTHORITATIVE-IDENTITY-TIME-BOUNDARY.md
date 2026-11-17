# Gate 6: authoritative identity and time boundary

Extract this archive at the repository root. It places:

- src/nse_quant/data_platform/native_authoritative_identity_time_boundary.py
- tests/data_platform/test_native_authoritative_identity_time_boundary.py
- README-GATE6-AUTHORITATIVE-IDENTITY-TIME-BOUNDARY.md

This is the next narrowly scoped native gate increment after the end-to-end
decision-run pipeline. It validates independently evidenced canonical underlying
identity, derivative binding, and authorized revocation.

Run:

uv run pytest tests/data_platform/test_native_authoritative_identity_time_boundary.py -x -q --tb=short
uv run pytest tests/data_platform -q
uv run ruff check src/nse_quant/data_platform tests/data_platform
uv run mypy
git diff --check

No eligibility, live trading, healing, backfill, adoption, or execution
authority. POINT_IN_TIME_DECISION remains rejected. All seven native gates
remain open; package QA is not platform acceptance.
