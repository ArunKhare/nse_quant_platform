"""Requirement-to-candidate-field mapping.

Maps each of the 9 requirements in native_strategy_requirements.py to actual
candidate fields (from research_iv_store.py's persist_research_iv_build return
dict and NativeResearchIvCandidate fields), flagging unmapped requirements,
without granting eligibility or enabling live trading. Addresses the
"reconcile uncovered inputs against the accepted current candidate" sub-gap of
gate 6 from docs/CURRENT_NATIVE_STATUS.md.
"""

from __future__ import annotations

import json
from typing import Any

# Requirement -> candidate field candidates (top-level or nested result_json)
REQUIREMENT_FIELD_CANDIDATES: dict[str, tuple[str, ...]] = {
    "chain_time_expiry_spot": ("chain_ts", "expiry", "spot", "atm_strike"),
    "option_chain_and_contract_terms": (
        "option_chain",
        "contract_terms",
        "lot_quantity",
        "ltp",
        "bid",
        "ask",
    ),
    "market_session": ("is_market_open", "market_session"),
    "iv_rank_and_history": ("iv_rank", "iv_history", "observation_count"),
    "iv_rv_spread": ("iv_rv_spread", "iv_spread"),
    "expected_move": ("expected_move_points", "expected_move"),
    "candidate_liquidity": ("oi", "volume", "spread", "depth"),
    "effective_proposal_configuration": (
        "wing_distance",
        "minimum_credit",
        "analytics_threshold",
        "liquidity_limit",
    ),
    "authoritative_identity_and_time": (
        "option_build_id",
        "spot_build_id",
        "terms_pin",
        "definition_hash",
        "evidence_fingerprint",
    ),
}


def map_requirements_to_fields(
    *,
    candidate: dict[str, Any],
) -> dict[str, Any]:
    """Map each requirement to actual candidate fields, flagging unmapped ones."""
    if type(candidate) is not dict:
        return dict(
            mapped=False,
            reason="CANDIDATE_OBJECT_REQUIRED",
            mapping={name: [] for name in REQUIREMENT_FIELD_CANDIDATES},
            unmapped=list(REQUIREMENT_FIELD_CANDIDATES),
        )

    # Flatten candidate keys (top-level + nested result_json if present)
    keys = set(candidate.keys())
    result_json = candidate.get("result_json")
    if isinstance(result_json, str):
        try:
            parsed = json.loads(result_json)
            if isinstance(parsed, dict):
                keys |= set(parsed.keys())
        except (ValueError, TypeError):
            pass

    mapping: dict[str, list[str]] = {}
    unmapped: list[str] = []
    for name, candidates in REQUIREMENT_FIELD_CANDIDATES.items():
        matched = [field for field in candidates if field in keys]
        mapping[name] = matched
        if not matched:
            unmapped.append(name)

    return dict(
        mapped=not unmapped,
        reason="ALL_REQUIREMENTS_MAPPED" if not unmapped else "UNMAPPED_REQUIREMENTS_REMAIN",
        mapping=mapping,
        unmapped=unmapped,
        requirements_count=len(REQUIREMENT_FIELD_CANDIDATES),
    )
