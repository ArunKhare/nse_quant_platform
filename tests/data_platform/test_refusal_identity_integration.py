"""Tests for refusal-to-identity integration."""

from __future__ import annotations

from nse_quant.data_platform.refusal_identity_integration import (
    integrate_refusal_into_identity,
)


def _valid_refusal_governance_result():
    return dict(
        integrated=True,
        reason="REFUSAL_INTEGRATED_INTO_GOVERNANCE",
        authenticated=True,
    )


def _valid_binding():
    return dict(
        underlying="NIFTY",
        derivative="NIFTY-OPT",
        signature_hex="a" * 128,
    )


def _valid_verification_key():
    return b"b" * 32


def test_non_dict_refusal_governance_result_refused():
    result = integrate_refusal_into_identity(
        refusal_governance_result="not_a_dict",
        binding=_valid_binding(),
        revocation_record=None,
        verification_key=_valid_verification_key(),
    )
    assert result["integrated"] is False
    assert result["reason"] == "REFUSAL_GOVERNANCE_RESULT_OBJECT_REQUIRED"
    assert result["valid"] is False


def test_refusal_not_integrated_rejected():
    candidate = _valid_refusal_governance_result()
    candidate["integrated"] = False
    result = integrate_refusal_into_identity(
        refusal_governance_result=candidate,
        binding=_valid_binding(),
        revocation_record=None,
        verification_key=_valid_verification_key(),
    )
    assert result["integrated"] is False
    assert result["reason"] == "REFUSAL_NOT_INTEGRATED_INTO_GOVERNANCE"
    assert result["valid"] is False


def test_missing_integrated_flag_defaults_to_false():
    candidate = _valid_refusal_governance_result()
    del candidate["integrated"]
    result = integrate_refusal_into_identity(
        refusal_governance_result=candidate,
        binding=_valid_binding(),
        revocation_record=None,
        verification_key=_valid_verification_key(),
    )
    assert result["integrated"] is False
    assert result["reason"] == "REFUSAL_NOT_INTEGRATED_INTO_GOVERNANCE"
    assert result["valid"] is False


def test_non_dict_binding_refused():
    result = integrate_refusal_into_identity(
        refusal_governance_result=_valid_refusal_governance_result(),
        binding="not_a_dict",
        revocation_record=None,
        verification_key=_valid_verification_key(),
    )
    assert result["integrated"] is False
    assert result["reason"] == "BINDING_OBJECT_REQUIRED"
    assert result["valid"] is False


def test_invalid_signature_identity_not_valid():
    result = integrate_refusal_into_identity(
        refusal_governance_result=_valid_refusal_governance_result(),
        binding=_valid_binding(),
        revocation_record=None,
        verification_key=_valid_verification_key(),
    )
    assert result["integrated"] is False
    assert result["reason"] == "IDENTITY_NOT_VALID"
    assert result["valid"] is False
