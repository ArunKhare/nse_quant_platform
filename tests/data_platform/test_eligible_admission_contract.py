"""Tests for the new sufficient eligible publication/admission contract."""

from __future__ import annotations

from nse_quant.data_platform.eligible_admission_contract import (
    AdmissionRequest,
    evaluate_admission_contract,
)


def _request(kind: str = "PUBLICATION"):
    return AdmissionRequest(
        namespace="nse-quant",
        authority_id="gov-root-1",
        underlying="NIFTY",
        derivative="NIFTY24JAN24000CE",
        knowledge_cutoff="2026-01-05T10:00:00+00:00",
        economic_at="2026-01-05T10:00:00+00:00",
        request_kind=kind,
    )


def test_all_checks_pass_eligible():
    result = evaluate_admission_contract(
        request=_request(),
        authority_authenticated=True,
        identity_valid=True,
        temporal_matched=True,
        lifecycle_resolved=True,
    )
    assert result.eligible is True
    assert result.reasons == []
    assert len(result.checks) == 4


def test_point_in_time_decision_rejected():
    result = evaluate_admission_contract(
        request=_request(kind="POINT_IN_TIME_DECISION"),
        authority_authenticated=True,
        identity_valid=True,
        temporal_matched=True,
        lifecycle_resolved=True,
    )
    assert result.eligible is False
    assert "POINT_IN_TIME_DECISION_REJECTED" in result.reasons


def test_authority_not_authenticated_refused():
    result = evaluate_admission_contract(
        request=_request(),
        authority_authenticated=False,
        identity_valid=True,
        temporal_matched=True,
        lifecycle_resolved=True,
    )
    assert result.eligible is False
    assert "AUTHORITY_NOT_AUTHENTICATED" in result.reasons


def test_identity_not_valid_refused():
    result = evaluate_admission_contract(
        request=_request(),
        authority_authenticated=True,
        identity_valid=False,
        temporal_matched=True,
        lifecycle_resolved=True,
    )
    assert result.eligible is False
    assert "IDENTITY_NOT_VALID" in result.reasons


def test_temporal_not_matched_refused():
    result = evaluate_admission_contract(
        request=_request(),
        authority_authenticated=True,
        identity_valid=True,
        temporal_matched=False,
        lifecycle_resolved=True,
    )
    assert result.eligible is False
    assert "TEMPORAL_NOT_MATCHED" in result.reasons


def test_lifecycle_not_resolved_refused():
    result = evaluate_admission_contract(
        request=_request(),
        authority_authenticated=True,
        identity_valid=True,
        temporal_matched=True,
        lifecycle_resolved=False,
    )
    assert result.eligible is False
    assert "LIFECYCLE_NOT_RESOLVED" in result.reasons
