"""Tests for independent time-evidence cross-check."""

from __future__ import annotations

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nse_quant.data_platform.independent_time_evidence import (
    cross_check_declared_time,
)


def _key_and_signature(attested_time: str):
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    signature = private_key.sign(attested_time.encode("utf-8"))
    return public_key.public_bytes_raw(), signature.hex()


def test_matching_times_consistent():
    attested = "2026-01-05T10:00:00+00:00"
    key, sig_hex = _key_and_signature(attested)
    result = cross_check_declared_time(
        declared_time=attested,
        attestation=dict(attested_time=attested, signature_hex=sig_hex),
        verification_key=key,
    )
    assert result["consistent"] is True
    assert result["reason"] == "DECLARED_MATCHES_INDEPENDENTLY_ATTESTED"


def test_mismatched_times_inconsistent():
    attested = "2026-01-05T10:00:00+00:00"
    key, sig_hex = _key_and_signature(attested)
    result = cross_check_declared_time(
        declared_time="2026-01-05T10:00:01+00:00",
        attestation=dict(attested_time=attested, signature_hex=sig_hex),
        verification_key=key,
    )
    assert result["consistent"] is False
    assert result["reason"] == "DECLARED_MISMATCHES_INDEPENDENTLY_ATTESTED"


def test_invalid_signature_refused():
    attested = "2026-01-05T10:00:00+00:00"
    key, _ = _key_and_signature(attested)
    result = cross_check_declared_time(
        declared_time=attested,
        attestation=dict(attested_time=attested, signature_hex="00" * 64),
        verification_key=key,
    )
    assert result["consistent"] is False
    assert result["reason"] == "SIGNATURE_INVALID"


def test_missing_attested_time_refused():
    key, sig_hex = _key_and_signature("2026-01-05T10:00:00+00:00")
    result = cross_check_declared_time(
        declared_time="2026-01-05T10:00:00+00:00",
        attestation=dict(signature_hex=sig_hex),
        verification_key=key,
    )
    assert result["consistent"] is False
    assert result["reason"] == "ATTESTED_TIME_REQUIRED"


def test_invalid_key_refused():
    result = cross_check_declared_time(
        declared_time="2026-01-05T10:00:00+00:00",
        attestation=dict(attested_time="2026-01-05T10:00:00+00:00", signature_hex="00" * 128),
        verification_key=b"short",
    )
    assert result["consistent"] is False
    assert result["reason"] == "VERIFICATION_KEY_INVALID"
