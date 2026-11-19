"""Semantic contract validation for requirement-candidate field mappings.

Validates that the mapped fields actually satisfy each requirement's semantic
contract (e.g., iv_rank_and_history needs nullable IV rank + observation count
+ cold-start policy), without granting eligibility or enabling live trading.
Addresses the "semantic contract validation" sub-gap of gate 6 from
docs/CURRENT_NATIVE_STATUS.md.
"""

from __future__ import annotations

from typing import Any

SEMANTIC_CONTRACTS: dict[str, dict[str, Any]] = {
    "iv_rank_and_history": dict(
        required_fields=("iv_rank", "observation_count", "cold_start_policy"),
        validators=dict(
            iv_rank=lambda v: v is None or isinstance(v, (int, float)),
            observation_count=lambda v: isinstance(v, int) and v >= 0,
            cold_start_policy=lambda v: v in ("reject", "warn", "allow"),
        ),
    ),
    "iv_rv_spread": dict(
        required_fields=("iv_rv_spread",),
        validators=dict(
            iv_rv_spread=lambda v: isinstance(v, (int, float)),
        ),
    ),
    "expected_move": dict(
        required_fields=("expected_move_points",),
        validators=dict(
            expected_move_points=lambda v: isinstance(v, (int, float)) and v > 0,
        ),
    ),
    "candidate_liquidity": dict(
        required_fields=("oi", "volume", "spread"),
        validators=dict(
            oi=lambda v: isinstance(v, int) and v >= 0,
            volume=lambda v: isinstance(v, int) and v >= 0,
            spread=lambda v: isinstance(v, (int, float)) and v >= 0,
        ),
    ),
}


def validate_semantic_contracts(
    *,
    candidate: dict[str, Any],
) -> dict[str, Any]:
    """Validate that mapped fields satisfy each requirement's semantic contract."""
    if type(candidate) is not dict:
        return dict(
            valid=False,
            reason="CANDIDATE_OBJECT_REQUIRED",
            violations={name: ["CANDIDATE_OBJECT_REQUIRED"] for name in SEMANTIC_CONTRACTS},
        )

    violations: dict[str, list[str]] = {}
    for name, contract in SEMANTIC_CONTRACTS.items():
        issues: list[str] = []
        for field in contract["required_fields"]:
            if field not in candidate:
                issues.append(f"MISSING_FIELD:{field}")
                continue
            validator = contract["validators"].get(field)
            if validator is not None and not validator(candidate[field]):
                issues.append(f"INVALID_VALUE:{field}")
        if issues:
            violations[name] = issues

    valid = not violations
    return dict(
        valid=valid,
        reason="ALL_SEMANTIC_CONTRACTS_SATISFIED" if valid else "SEMANTIC_CONTRACT_VIOLATIONS",
        violations=violations,
    )
