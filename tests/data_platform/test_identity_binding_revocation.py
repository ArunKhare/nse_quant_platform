"""Tests for identity binding and authorized revocation."""

from __future__ import annotations

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nse_quant.data_platform.identity_binding_revocation import (
    validate_identity_binding,
)


def _key_and_signatures(underlying: str, derivative: str):
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    binding_sig = private_key.sign(f"{underlying}->{derivative}".encode())
    rev_sig = private_key.sign(f"REVOKE:{underlying}->{derivative}".encode())
    return (
        public_key.public_bytes_raw(),
        binding_sig.hex(),
        rev_sig.hex(),
    )


def test_valid_binding_not_revoked():
    key, binding_sig, _ = _key_and_signatures("NIFTY", "NIFTY24JAN24000CE")
    result = validate_identity_binding(
        binding=dict(underlying="NIFTY", derivative="NIFTY24JAN24000CE", signature_hex=binding_sig),
        revocation_record=None,
        verification_key=key,
    )
    assert result["valid"] is True
    assert result["reason"] == "BINDING_VALID"
    assert result["revoked"] is False


def test_valid_binding_revoked():
    key, binding_sig, rev_sig = _key_and_signatures("NIFTY", "NIFTY24JAN24000CE")
    result = validate_identity_binding(
        binding=dict(underlying="NIFTY", derivative="NIFTY24JAN24000CE", signature_hex=binding_sig),
        revocation_record=dict(revoked=True, signature_hex=rev_sig),
        verification_key=key,
    )
    assert result["valid"] is False
    assert result["reason"] == "BINDING_REVOKED"
    assert result["revoked"] is True


def test_invalid_binding_signature_refused():
    key, _, _ = _key_and_signatures("NIFTY", "NIFTY24JAN24000CE")
    result = validate_identity_binding(
        binding=dict(underlying="NIFTY", derivative="NIFTY24JAN24000CE", signature_hex="00" * 64),
        revocation_record=None,
        verification_key=key,
    )
    assert result["valid"] is False
    assert result["reason"] == "SIGNATURE_INVALID"


def test_invalid_revocation_signature_refused():
    key, binding_sig, _ = _key_and_signatures("NIFTY", "NIFTY24JAN24000CE")
    result = validate_identity_binding(
        binding=dict(underlying="NIFTY", derivative="NIFTY24JAN24000CE", signature_hex=binding_sig),
        revocation_record=dict(revoked=True, signature_hex="00" * 64),
        verification_key=key,
    )
    assert result["valid"] is False
    assert result["reason"] == "REVOCATION_SIGNATURE_INVALID"


def test_missing_underlying_refused():
    key, binding_sig, _ = _key_and_signatures("NIFTY", "NIFTY24JAN24000CE")
    result = validate_identity_binding(
        binding=dict(derivative="NIFTY24JAN24000CE", signature_hex=binding_sig),
        revocation_record=None,
        verification_key=key,
    )
    assert result["valid"] is False
    assert result["reason"] == "UNDERLYING_REQUIRED"


def test_invalid_key_refused():
    result = validate_identity_binding(
        binding=dict(underlying="NIFTY", derivative="NIFTY24JAN24000CE", signature_hex="00" * 128),
        revocation_record=None,
        verification_key=b"short",
    )
    assert result["valid"] is False
    assert result["reason"] == "VERIFICATION_KEY_INVALID"
