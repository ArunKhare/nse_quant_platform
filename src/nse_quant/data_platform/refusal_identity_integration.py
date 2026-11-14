"""Refusal-to-identity integration.

Integrates the refusal governance integration's output (refusal_governance_integration.py)
into the identity binding revocation evaluation (identity_binding_revocation.py),
without granting eligibility or enabling live trading. Addresses the "integrate
the refusal governance integration's output into the identity binding revocation
evaluation" sub-gap of gate 2 from docs/CURRENT_NATIVE_STATUS.md.
"""

from __future__ import annotations

from typing import Any

from nse_quant.data_platform.identity_binding_revocation import (
    validate_identity_binding,
)


def integrate_refusal_into_identity(
    *,
    refusal_governance_result: dict[str, Any],
    binding: dict[str, Any],
    revocation_record: dict[str, Any] | None,
    verification_key: bytes,
) -> dict[str, Any]:
    """Integrate the refusal governance integration's output into the identity binding
    revocation evaluation."""
    if type(refusal_governance_result) is not dict:
        return dict(
            integrated=False,
            reason="REFUSAL_GOVERNANCE_RESULT_OBJECT_REQUIRED",
            valid=False,
        )
    if type(binding) is not dict:
        return dict(
            integrated=False,
            reason="BINDING_OBJECT_REQUIRED",
            valid=False,
        )

    refusal_integrated = refusal_governance_result.get("integrated", False)
    if type(refusal_integrated) is not bool:
        refusal_integrated = False

    if not refusal_integrated:
        return dict(
            integrated=False,
            reason="REFUSAL_NOT_INTEGRATED_INTO_GOVERNANCE",
            valid=False,
        )

    identity = validate_identity_binding(
        binding=binding,
        revocation_record=revocation_record,
        verification_key=verification_key,
    )
    integrated = identity.get("valid", False)
    return dict(
        integrated=integrated,
        reason="REFUSAL_INTEGRATED_INTO_IDENTITY" if integrated else "IDENTITY_NOT_VALID",
        valid=integrated,
    )
