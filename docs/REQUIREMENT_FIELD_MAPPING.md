# Requirement-to-candidate-field mapping

`map_requirements_to_fields` maps each of the 9 requirements in `native_strategy_requirements.py` to actual candidate fields (from `research_iv_store.py`'s `persist_research_iv_build` return dict and `NativeResearchIvCandidate` fields), flagging unmapped requirements.

## Contract

- Input: candidate dict (may include nested `result_json` string).
- Output: dict with mapped, reason, mapping, unmapped, requirements_count.
- Safety: never grants eligibility, never enables live trading.

## Rules

- Mapped when at least one candidate field matches for the requirement.
- Unmapped when no candidate field matches.
- Refuses non-dict candidate.
- Addresses the "reconcile uncovered inputs against the accepted current candidate" sub-gap of gate 6 from docs/CURRENT_NATIVE_STATUS.md.
