# Candidate reconciliation against the accepted current candidate

`reconcile_candidate` reconciles a candidate's version/fingerprint against the requirements inventory (`native_strategy_requirements.py`), flagging drift or mismatch without synthesizing identity or granting eligibility.

## Contract

- Input: candidate_version (str), candidate_fingerprint (str).
- Output: dict with reconciled, reason, version_match, fingerprint_match, expected_version, expected_fingerprint, requirements_count.
- Safety: never synthesizes identity, never grants eligibility, never enables live trading.

## Rules

- Reconciled only when both version and fingerprint match.
- Refuses missing version/fingerprint.
- Addresses the "reconcile uncovered inputs against the accepted current candidate" sub-gap of gate 6 from docs/CURRENT_NATIVE_STATUS.md.
