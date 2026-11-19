"""Requirements-vs-candidate coverage reconciliation.

Checks which of the 9 requirements in native_strategy_requirements.py are
covered vs uncovered by the accepted current candidate (research_iv_store.py's
persist_research_iv_build output), without granting eligibility or enabling
live trading. Addresses the "reconcile uncovered inputs against the accepted
current candidate" sub-gap of gate 6 from docs/CURRENT_NATIVE_STATUS.md.
"""

from __future__ import annotations

from typing import Any

from nse_quant.data_platform.native_strategy_requirements import REQUIREMENTS

REQUIRED_NAMES = tuple(name for name, _, _ in REQUIREMENTS)


def reconcile_requirements_coverage(
    *,
    candidate: dict[str, Any],
) -> dict[str, Any]:
    """Check which requirements are covered vs uncovered by the candidate."""
    if type(candidate) is not dict:
        return dict(
            reconciled=False,
            reason="CANDIDATE_OBJECT_REQUIRED",
            covered=[],
            uncovered=list(REQUIRED_NAMES),
        )

    # Flatten candidate keys (top-level + nested result_json if present) for coverage check
    keys = set(candidate.keys())
    result_json = candidate.get("result_json")
    if isinstance(result_json, str):
        import json

        try:
            parsed = json.loads(result_json)
            if isinstance(parsed, dict):
                keys |= set(parsed.keys())
        except (ValueError, TypeError):
            pass

    covered = [name for name in REQUIRED_NAMES if name in keys]
    uncovered = [name for name in REQUIRED_NAMES if name not in keys]
    reconciled = not uncovered
    return dict(
        reconciled=reconciled,
        reason="ALL_REQUIREMENTS_COVERED" if reconciled else "UNCOVERED_REQUIREMENTS_REMAIN",
        covered=covered,
        uncovered=uncovered,
        requirements_count=len(REQUIRED_NAMES),
    )
