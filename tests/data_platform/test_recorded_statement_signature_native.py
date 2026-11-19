"""Actual native fixture and crypto composition; no simulated stores."""

from dataclasses import replace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from test_identity_statement_reader_native import body
from test_identity_statement_reader_native import source_claim as source_claim

from nse_quant.data_platform import identity_statement_document as document
from nse_quant.data_platform import recorded_statement_signature as binding
from nse_quant.data_platform import statement_signature as crypto


def inputs(claim, kind="ASSERTED"):
    registry, bronze, request, saved, plan, _, _, _ = claim
    payload = body(assertion=kind) + b"\n"
    private = Ed25519PrivateKey.generate()
    key = private.public_key().public_bytes_raw()
    return dict(
        registry=registry,
        bronze=bronze,
        assertion_id=saved["assertion_id"],
        request=request,
        record_id="r1",
        original_plan=plan,
        expected_plan_sha256=document.sha(plan),
        payload=payload,
        signature=private.sign(crypto.signing_message(payload)),
        public_key=key,
        expected_public_key_sha256=document.sha(key),
    )


def test_native_recording_is_bound_without_authority(source_claim):
    args = inputs(source_claim())
    result = binding.inspect_recorded_statement_signature(**args)
    assert result.recorded_payload_signature_bound
    assert result.signature.cryptographic_signature_verified
    assert result.evidence_fingerprint == (
        binding.inspect_recorded_statement_signature(**args).evidence_fingerprint
    )
    assert not result.issuer_authenticated
    assert not result.namespace_authority_verified
    assert not result.identity_verified
    assert not result.authorized_revocation_asserted
    assert not result.decision_eligibility_asserted
    assert not result.signature_acquisition_provenance_verified
    assert result.canonical_underlying_id is None


@pytest.mark.parametrize("kind", ["DISPUTED", "WITHDRAWN"])
def test_signed_statement_kind_is_not_authorized_revocation(source_claim, kind):
    result = binding.inspect_recorded_statement_signature(
        **inputs(source_claim(claim_kind=kind), kind)
    )
    assert result.recorded_payload_signature_bound
    assert not result.authorized_revocation_asserted


def test_bad_key_pin_retains_both_native_observations(source_claim):
    args = inputs(source_claim())
    args["expected_public_key_sha256"] = "0" * 64
    result = binding.inspect_recorded_statement_signature(**args)
    assert result.status == "review_required"
    assert result.content_after is not None
    assert not result.recorded_payload_signature_bound


def test_different_payload_cannot_attach_to_recording(source_claim):
    args = inputs(source_claim())
    args["payload"] = args["payload"] + b"\n"
    with pytest.raises(ValueError, match="PIN_MISMATCH"):
        binding.inspect_recorded_statement_signature(**args)


def test_actual_retry_between_native_observations_requires_review(source_claim, monkeypatch):
    claim = source_claim()
    args = inputs(claim)
    real = crypto.verify_pinned_statement_signature

    def observe_retry(*positional, **keywords):
        value = real(*positional, **keywords)
        claim[5]()
        return value

    monkeypatch.setattr(crypto, "verify_pinned_statement_signature", observe_retry)
    result = binding.inspect_recorded_statement_signature(**args)
    assert result.status == "review_required"
    assert not result.recorded_payload_signature_bound
    assert "RECORDED_CONTENT_CHANGED_OR_INCOMPLETE_AFTER_SIGNATURE" in result.reason_codes


def test_old_pin_stops_before_crypto(source_claim, monkeypatch):
    claim = source_claim()
    args = inputs(claim)
    claim[5](replace(claim[2], assertion="WITHDRAWN"))

    def forbidden(*positional, **keywords):
        raise AssertionError("Invalid recording reached signature verification")

    monkeypatch.setattr(crypto, "verify_pinned_statement_signature", forbidden)
    result = binding.inspect_recorded_statement_signature(**args)
    assert result.status == "review_required"
    assert result.signature is None
    assert result.content_after is None


def test_invalid_signature_cannot_bind_good_native_content(source_claim):
    args = inputs(source_claim())
    args["signature"] = bytes(64)
    result = binding.inspect_recorded_statement_signature(**args)
    assert result.content_before.statement_content_matched
    assert result.content_after.statement_content_matched
    assert not result.signature.cryptographic_signature_verified
    assert not result.recorded_payload_signature_bound
