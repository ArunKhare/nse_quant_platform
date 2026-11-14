"""Refusal-to-admission integration.

Integrates the refusal time evidence integration's output (refusal_time_evidence_integration.py)
into the eligible admission contract evaluation (eligible_admission_contract.py),
without granting eligibility or enabling live trading. Addresses the "integrate
the refusal time evidence integration's output into the eligible admission
contract evaluation" sub-gap of gate 4 from docs/CURRENT_NATIVE_STATUS.md.
"""

from __future__ import annotations

from typing import Any

from nse_quant.data_platform.eligible_admission_contract import (
    AdmissionRequest,
    evaluate_admission_contract,
)


def integrate_refusal_into_admission(
    *,
    refusal_time_evidence_result: dict[str, Any],
    request: AdmissionRequest,
    authority_authenticated: bool,
    identity_valid: bool,
    temporal_matched: bool,
    lifecycle_resolved: bool,
) -> dict[str, Any]:
    """Integrate the refusal time evidence integration's output into the eligible admission
    contract evaluation."""
    if type(refusal_time_evidence_result) is not dict:
        return dict(
            integrated=False,
            reason="REFUSAL_TIME_EVIDENCE_RESULT_OBJECT_REQUIRED",
            eligible=False,
        )
    if type(request) is not AdmissionRequest:
        return dict(
            integrated=False,
            reason="INVALID_REQUEST",
            eligible=False,
        )

    refusal_integrated = refusal_time_evidence_result.get("integrated", False)
    if type(refusal_integrated) is not bool:
        refusal_integrated = False

    if not refusal_integrated:
        return dict(
            integrated=False,
            reason="REFUSAL_NOT_INTEGRATED_INTO_TIME_EVIDENCE",
            eligible=False,
        )

    admission = evaluate_admission_contract(
        request=request,
        authority_authenticated=authority_authenticated,
        identity_valid=identity_valid,
        temporal_matched=temporal_matched,
        lifecycle_resolved=lifecycle_resolved,
    )
    integrated = admission.eligible
    return dict(
        integrated=integrated,
        reason="REFUSAL_INTEGRATED_INTO_ADMISSION" if integrated else "ADMISSION_NOT_ELIGIBLE",
        eligible=integrated,
    )
