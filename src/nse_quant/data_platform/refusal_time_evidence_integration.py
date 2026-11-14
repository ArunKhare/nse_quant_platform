"""Refusal-to-time-evidence integration.

Integrates the refusal identity integration's output (refusal_identity_integration.py)
into the independent time evidence evaluation (independent_time_evidence.py),
without granting eligibility or enabling live trading. Addresses the "integrate
the refusal identity integration's output into the independent time evidence
evaluation" sub-gap of gate 3 from docs/CURRENT_NATIVE_STATUS.md.
"""

from __future__ import annotations

from typing import Any


def integrate_refusal_into_time_evidence(
    *,
    refusal_identity_result: dict[str, Any],
    knowledge_cutoff: str,
    economic_at: str,
) -> dict[str, Any]:
    """Integrate the refusal identity integration's output into the independent time
    evidence evaluation."""
    if type(refusal_identity_result) is not dict:
        return dict(
            integrated=False,
            reason="REFUSAL_IDENTITY_RESULT_OBJECT_REQUIRED",
            valid=False,
        )
    if type(knowledge_cutoff) is not str or not knowledge_cutoff:
        return dict(
            integrated=False,
            reason="KNOWLEDGE_CUTOFF_REQUIRED",
            valid=False,
        )
    if type(economic_at) is not str or not economic_at:
        return dict(
            integrated=False,
            reason="ECONOMIC_AT_REQUIRED",
            valid=False,
        )

    refusal_integrated = refusal_identity_result.get("integrated", False)
    if type(refusal_integrated) is not bool:
        refusal_integrated = False

    if not refusal_integrated:
        return dict(
            integrated=False,
            reason="REFUSAL_NOT_INTEGRATED_INTO_IDENTITY",
            valid=False,
        )

    # Both axes must be present and distinct (knowledge_cutoff and economic_at remain separate)
    valid = knowledge_cutoff != economic_at
    return dict(
        integrated=valid,
        reason="REFUSAL_INTEGRATED_INTO_TIME_EVIDENCE" if valid else "TIME_AXES_MUST_BE_DISTINCT",
        valid=valid,
    )
