"""Tests for refusal-to-time-evidence integration."""

from __future__ import annotations

from nse_quant.data_platform.refusal_time_evidence_integration import (
    integrate_refusal_into_time_evidence,
)


def _valid_refusal_identity_result():
    return dict(
        integrated=True,
        reason="REFUSAL_INTEGRATED_INTO_IDENTITY",
        valid=True,
    )


def test_valid_refusal_identity_result_integrated():
    result = integrate_refusal_into_time_evidence(
        refusal_identity_result=_valid_refusal_identity_result(),
        knowledge_cutoff="2026-11-14T00:00:00Z",
        economic_at="2026-11-14T01:00:00Z",
    )
    assert result["integrated"] is True
    assert result["reason"] == "REFUSAL_INTEGRATED_INTO_TIME_EVIDENCE"
    assert result["valid"] is True


def test_non_dict_refusal_identity_result_refused():
    result = integrate_refusal_into_time_evidence(
        refusal_identity_result="not_a_dict",
        knowledge_cutoff="2026-11-14T00:00:00Z",
        economic_at="2026-11-14T01:00:00Z",
    )
    assert result["integrated"] is False
    assert result["reason"] == "REFUSAL_IDENTITY_RESULT_OBJECT_REQUIRED"
    assert result["valid"] is False


def test_refusal_not_integrated_rejected():
    candidate = _valid_refusal_identity_result()
    candidate["integrated"] = False
    result = integrate_refusal_into_time_evidence(
        refusal_identity_result=candidate,
        knowledge_cutoff="2026-11-14T00:00:00Z",
        economic_at="2026-11-14T01:00:00Z",
    )
    assert result["integrated"] is False
    assert result["reason"] == "REFUSAL_NOT_INTEGRATED_INTO_IDENTITY"
    assert result["valid"] is False


def test_missing_integrated_flag_defaults_to_false():
    candidate = _valid_refusal_identity_result()
    del candidate["integrated"]
    result = integrate_refusal_into_time_evidence(
        refusal_identity_result=candidate,
        knowledge_cutoff="2026-11-14T00:00:00Z",
        economic_at="2026-11-14T01:00:00Z",
    )
    assert result["integrated"] is False
    assert result["reason"] == "REFUSAL_NOT_INTEGRATED_INTO_IDENTITY"
    assert result["valid"] is False


def test_missing_knowledge_cutoff_refused():
    result = integrate_refusal_into_time_evidence(
        refusal_identity_result=_valid_refusal_identity_result(),
        knowledge_cutoff="",
        economic_at="2026-11-14T01:00:00Z",
    )
    assert result["integrated"] is False
    assert result["reason"] == "KNOWLEDGE_CUTOFF_REQUIRED"
    assert result["valid"] is False


def test_missing_economic_at_refused():
    result = integrate_refusal_into_time_evidence(
        refusal_identity_result=_valid_refusal_identity_result(),
        knowledge_cutoff="2026-11-14T00:00:00Z",
        economic_at="",
    )
    assert result["integrated"] is False
    assert result["reason"] == "ECONOMIC_AT_REQUIRED"
    assert result["valid"] is False


def test_same_time_axes_rejected():
    result = integrate_refusal_into_time_evidence(
        refusal_identity_result=_valid_refusal_identity_result(),
        knowledge_cutoff="2026-11-14T00:00:00Z",
        economic_at="2026-11-14T00:00:00Z",
    )
    assert result["integrated"] is False
    assert result["reason"] == "TIME_AXES_MUST_BE_DISTINCT"
    assert result["valid"] is False
