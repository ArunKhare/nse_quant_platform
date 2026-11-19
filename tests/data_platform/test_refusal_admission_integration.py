"""Tests for refusal-to-admission integration."""

from __future__ import annotations

from nse_quant.data_platform.eligible_admission_contract import AdmissionRequest
from nse_quant.data_platform.refusal_admission_integration import (
    integrate_refusal_into_admission,
)


def _valid_refusal_time_evidence_result():
    return dict(
        integrated=True,
        reason="REFUSAL_INTEGRATED_INTO_TIME_EVIDENCE",
        valid=True,
    )


def _valid_request():
    return AdmissionRequest(
        namespace="test-namespace",
        authority_id="test-authority",
        underlying="NIFTY",
        derivative="NIFTY-OPT",
        knowledge_cutoff="2026-11-14T00:00:00Z",
        economic_at="2026-11-14T01:00:00Z",
        request_kind="RESEARCH",
    )


def test_valid_refusal_time_evidence_result_integrated():
    result = integrate_refusal_into_admission(
        refusal_time_evidence_result=_valid_refusal_time_evidence_result(),
        request=_valid_request(),
        authority_authenticated=True,
        identity_valid=True,
        temporal_matched=True,
        lifecycle_resolved=True,
    )
    assert result["integrated"] is True
    assert result["reason"] == "REFUSAL_INTEGRATED_INTO_ADMISSION"
    assert result["eligible"] is True


def test_non_dict_refusal_time_evidence_result_refused():
    result = integrate_refusal_into_admission(
        refusal_time_evidence_result="not_a_dict",
        request=_valid_request(),
        authority_authenticated=True,
        identity_valid=True,
        temporal_matched=True,
        lifecycle_resolved=True,
    )
    assert result["integrated"] is False
    assert result["reason"] == "REFUSAL_TIME_EVIDENCE_RESULT_OBJECT_REQUIRED"
    assert result["eligible"] is False


def test_refusal_not_integrated_rejected():
    candidate = _valid_refusal_time_evidence_result()
    candidate["integrated"] = False
    result = integrate_refusal_into_admission(
        refusal_time_evidence_result=candidate,
        request=_valid_request(),
        authority_authenticated=True,
        identity_valid=True,
        temporal_matched=True,
        lifecycle_resolved=True,
    )
    assert result["integrated"] is False
    assert result["reason"] == "REFUSAL_NOT_INTEGRATED_INTO_TIME_EVIDENCE"
    assert result["eligible"] is False


def test_missing_integrated_flag_defaults_to_false():
    candidate = _valid_refusal_time_evidence_result()
    del candidate["integrated"]
    result = integrate_refusal_into_admission(
        refusal_time_evidence_result=candidate,
        request=_valid_request(),
        authority_authenticated=True,
        identity_valid=True,
        temporal_matched=True,
        lifecycle_resolved=True,
    )
    assert result["integrated"] is False
    assert result["reason"] == "REFUSAL_NOT_INTEGRATED_INTO_TIME_EVIDENCE"
    assert result["eligible"] is False


def test_non_request_refused():
    result = integrate_refusal_into_admission(
        refusal_time_evidence_result=_valid_refusal_time_evidence_result(),
        request="not_a_request",
        authority_authenticated=True,
        identity_valid=True,
        temporal_matched=True,
        lifecycle_resolved=True,
    )
    assert result["integrated"] is False
    assert result["reason"] == "INVALID_REQUEST"
    assert result["eligible"] is False


def test_point_in_time_decision_rejected():
    request = AdmissionRequest(
        namespace="test-namespace",
        authority_id="test-authority",
        underlying="NIFTY",
        derivative="NIFTY-OPT",
        knowledge_cutoff="2026-11-14T00:00:00Z",
        economic_at="2026-11-14T01:00:00Z",
        request_kind="POINT_IN_TIME_DECISION",
    )
    result = integrate_refusal_into_admission(
        refusal_time_evidence_result=_valid_refusal_time_evidence_result(),
        request=request,
        authority_authenticated=True,
        identity_valid=True,
        temporal_matched=True,
        lifecycle_resolved=True,
    )
    assert result["integrated"] is False
    assert result["reason"] == "ADMISSION_NOT_ELIGIBLE"
    assert result["eligible"] is False
