# Gate 6: decision-loop evidence integration

Extract this archive at the repository root. It places:

- src/nse_quant/data_platform/native_iron_condor_decision_loop_evidence_integration.py
- tests/data_platform/test_native_iron_condor_decision_loop_evidence_integration.py
- README-GATE6-DECISION-LOOP-EVIDENCE-INTEGRATION.md

This upgrades the decision-loop integration to validate coverage evidence links
and the authoritative identity/time boundary, embed both exact contexts in a
reconciliation, persist it, and exactly replay it.

Run:

uv run pytest tests/data_platform/test_native_iron_condor_decision_loop_evidence_integration.py -x -q --tb=short
uv run pytest tests/data_platform -q
uv run ruff check src/nse_quant/data_platform tests/data_platform
uv run mypy
git diff --check

No eligibility, live trading, healing, backfill, adoption, or execution
authority. POINT_IN_TIME_DECISION remains rejected. All seven native gates
remain open; package QA is not platform acceptance.
