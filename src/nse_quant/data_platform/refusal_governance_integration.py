"""Refusal-to-governance integration.

Integrates the refusal acceptance integration's output (refusal_acceptance_integration.py)
into the governance authority evaluation (governance_authority.py), without
granting eligibility or enabling live trading. Addresses the "integrate the
refusal acceptance integration's output into the governance authority evaluation"
sub-gap of gate 1 from docs/CURRENT_NATIVE_STATUS.md.
"""

from __future__ import annotations

from typing import Any

from nse_quant.data_platform.governance_authority import (
    authenticate_governance_authority,
)


def integrate_refusal_into_governance(
    *,
    refusal_acceptance_result: Any,
    authority_claim: dict[str, Any],
    attestation: dict[str, Any],
    verification_key: bytes,
) -> dict[str, Any]:
    """Integrate the refusal acceptance integration's output into the governance
    authority evaluation."""
    if type(refusal_acceptance_result) is not dict:
        return dict(
            integrated=False,
            reason="REFUSAL_ACCEPTANCE_RESULT_OBJECT_REQUIRED",
            authenticated=False,
        )
    if type(authority_claim) is not dict:
        return dict(
            integrated=False,
            reason="AUTHORITY_CLAIM_OBJECT_REQUIRED",
            authenticated=False,
        )
    if type(attestation) is not dict:
        return dict(
            integrated=False,
            reason="ATTESTATION_OBJECT_REQUIRED",
            authenticated=False,
        )

    refusal_accepted = refusal_acceptance_result.get("accepted", False)
    if type(refusal_accepted) is not bool:
        refusal_accepted = False

    if not refusal_accepted:
        return dict(
            integrated=False,
            reason="REFUSAL_NOT_ACCEPTED",
            authenticated=False,
        )

    governance = authenticate_governance_authority(
        authority_claim=authority_claim,
        attestation=attestation,
        verification_key=verification_key,
    )
    integrated = governance.get("authenticated", False)
    return dict(
        integrated=integrated,
        reason="REFUSAL_INTEGRATED_INTO_GOVERNANCE"
        if integrated
        else "GOVERNANCE_NOT_AUTHENTICATED",
        authenticated=integrated,
    )
