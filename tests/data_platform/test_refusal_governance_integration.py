"""Tests for refusal-to-governance integration."""

from __future__ import annotations

from nse_quant.data_platform.refusal_governance_integration import (
    integrate_refusal_into_governance,
)


def _valid_refusal_acceptance_result():
    return dict(
        accepted=True,
        reasons=[],
        checks=[],
        production_cutover_authorized=False,
        live_trading_authorized=False,
    )


def _valid_authority_claim():
    return dict(
        namespace="test-namespace",
        authority_id="test-authority",
        signature_hex="a" * 128,
    )


def _valid_attestation():
    return dict(
        attested_namespace="test-namespace",
        attested_authority_id="test-authority",
        signature_hex="b" * 128,
    )


def _valid_verification_key():
    return b"c" * 32


def test_non_dict_refusal_acceptance_result_refused():
    result = integrate_refusal_into_governance(
        refusal_acceptance_result="not_a_dict",
        authority_claim=_valid_authority_claim(),
        attestation=_valid_attestation(),
        verification_key=_valid_verification_key(),
    )
    assert result["integrated"] is False
    assert result["reason"] == "REFUSAL_ACCEPTANCE_RESULT_OBJECT_REQUIRED"
    assert result["authenticated"] is False


def test_refusal_not_accepted_rejected():
    candidate = _valid_refusal_acceptance_result()
    candidate["accepted"] = False
    result = integrate_refusal_into_governance(
        refusal_acceptance_result=candidate,
        authority_claim=_valid_authority_claim(),
        attestation=_valid_attestation(),
        verification_key=_valid_verification_key(),
    )
    assert result["integrated"] is False
    assert result["reason"] == "REFUSAL_NOT_ACCEPTED"
    assert result["authenticated"] is False


def test_missing_accepted_flag_defaults_to_false():
    candidate = _valid_refusal_acceptance_result()
    del candidate["accepted"]
    result = integrate_refusal_into_governance(
        refusal_acceptance_result=candidate,
        authority_claim=_valid_authority_claim(),
        attestation=_valid_attestation(),
        verification_key=_valid_verification_key(),
    )
    assert result["integrated"] is False
    assert result["reason"] == "REFUSAL_NOT_ACCEPTED"
    assert result["authenticated"] is False


def test_non_dict_authority_claim_refused():
    result = integrate_refusal_into_governance(
        refusal_acceptance_result=_valid_refusal_acceptance_result(),
        authority_claim="not_a_dict",
        attestation=_valid_attestation(),
        verification_key=_valid_verification_key(),
    )
    assert result["integrated"] is False
    assert result["reason"] == "AUTHORITY_CLAIM_OBJECT_REQUIRED"
    assert result["authenticated"] is False


def test_non_dict_attestation_refused():
    result = integrate_refusal_into_governance(
        refusal_acceptance_result=_valid_refusal_acceptance_result(),
        authority_claim=_valid_authority_claim(),
        attestation="not_a_dict",
        verification_key=_valid_verification_key(),
    )
    assert result["integrated"] is False
    assert result["reason"] == "ATTESTATION_OBJECT_REQUIRED"
    assert result["authenticated"] is False


def test_invalid_signature_governance_not_authenticated():
    result = integrate_refusal_into_governance(
        refusal_acceptance_result=_valid_refusal_acceptance_result(),
        authority_claim=_valid_authority_claim(),
        attestation=_valid_attestation(),
        verification_key=_valid_verification_key(),
    )
    assert result["integrated"] is False
    assert result["reason"] == "GOVERNANCE_NOT_AUTHENTICATED"
    assert result["authenticated"] is False
