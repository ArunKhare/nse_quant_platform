"""New sufficient eligible publication/admission contract.

Evaluates a publication/admission request against a new sufficient contract
combining authority, identity, temporal evidence, and lifecycle checks, while
preserving the existing research @1's rejection of POINT_IN_TIME_DECISION.
Addresses gate 4 from docs/CURRENT_NATIVE_STATUS.md.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AdmissionRequest(BaseModel):
    namespace: str
    authority_id: str
    underlying: str
    derivative: str
    knowledge_cutoff: str
    economic_at: str
    request_kind: str  # must not be POINT_IN_TIME_DECISION


class AdmissionDecision(BaseModel):
    eligible: bool
    reasons: list[str] = Field(default_factory=list)
    checks: list[dict[str, Any]] = Field(default_factory=list)


def evaluate_admission_contract(
    *,
    request: AdmissionRequest,
    authority_authenticated: bool,
    identity_valid: bool,
    temporal_matched: bool,
    lifecycle_resolved: bool,
) -> AdmissionDecision:
    """Evaluate a publication/admission request against the new sufficient contract."""
    if type(request) is not AdmissionRequest:
        return AdmissionDecision(eligible=False, reasons=["INVALID_REQUEST"])

    checks: list[dict[str, Any]] = []
    reasons: list[str] = []

    # Preserve existing research @1 rejection of POINT_IN_TIME_DECISION
    if request.request_kind == "POINT_IN_TIME_DECISION":
        return AdmissionDecision(
            eligible=False,
            reasons=["POINT_IN_TIME_DECISION_REJECTED"],
            checks=[dict(check="request_kind", passed=False, kind=request.request_kind)],
        )

    checks.append(dict(check="authority_authenticated", passed=authority_authenticated))
    if not authority_authenticated:
        reasons.append("AUTHORITY_NOT_AUTHENTICATED")

    checks.append(dict(check="identity_valid", passed=identity_valid))
    if not identity_valid:
        reasons.append("IDENTITY_NOT_VALID")

    checks.append(dict(check="temporal_matched", passed=temporal_matched))
    if not temporal_matched:
        reasons.append("TEMPORAL_NOT_MATCHED")

    checks.append(dict(check="lifecycle_resolved", passed=lifecycle_resolved))
    if not lifecycle_resolved:
        reasons.append("LIFECYCLE_NOT_RESOLVED")

    return AdmissionDecision(
        eligible=not reasons,
        reasons=reasons,
        checks=checks,
    )
