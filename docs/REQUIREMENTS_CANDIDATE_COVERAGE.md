# Requirements-vs-candidate coverage reconciliation

`reconcile_requirements_coverage` checks which of the 9 requirements in `native_strategy_requirements.py` are covered vs uncovered by the accepted current candidate (`research_iv_store.py`'s `persist_research_iv_build` output).

## Contract

- Input: candidate dict (may include nested `result_json` string).
- Output: dict with reconciled, reason, covered, uncovered, requirements_count.
- Safety: never grants eligibility, never enables live trading.

## Rules

- Covered when the requirement name appears as a top-level or nested `result_json` key.
- Reconciled only when no requirements are uncovered.
- Refuses non-dict candidate.
- Addresses the "reconcile uncovered inputs against the accepted current candidate" sub-gap of gate 6 from docs/CURRENT_NATIVE_STATUS.md.
