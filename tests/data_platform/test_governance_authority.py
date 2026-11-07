"""Tests for governance/namespace authority authentication."""

from __future__ import annotations

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nse_quant.data_platform.governance_authority import (
    authenticate_governance_authority,
)


def _key_and_signatures(
    namespace: str,
    authority_id: str,
    *,
    claim_namespace: str | None = None,
    claim_authority_id: str | None = None,
):
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    claim_sig = private_key.sign(
        f"AUTHORITY:{claim_namespace or namespace}:{claim_authority_id or authority_id}".encode()
    )
    att_sig = private_key.sign(f"ATTEST:{namespace}:{authority_id}".encode())
    return public_key.public_bytes_raw(), claim_sig.hex(), att_sig.hex()


def test_matching_authority_authenticated():
    key, claim_sig, att_sig = _key_and_signatures("nse-quant", "gov-root-1")
    result = authenticate_governance_authority(
        authority_claim=dict(
            namespace="nse-quant", authority_id="gov-root-1", signature_hex=claim_sig
        ),
        attestation=dict(
            attested_namespace="nse-quant",
            attested_authority_id="gov-root-1",
            signature_hex=att_sig,
        ),
        verification_key=key,
    )
    assert result["authenticated"] is True
    assert result["reason"] == "AUTHORITY_AUTHENTICATED"


def test_namespace_mismatch_refused():
    key, claim_sig, att_sig = _key_and_signatures(
        "nse-quant", "gov-root-1", claim_namespace="other-ns"
    )
    result = authenticate_governance_authority(
        authority_claim=dict(
            namespace="other-ns", authority_id="gov-root-1", signature_hex=claim_sig
        ),
        attestation=dict(
            attested_namespace="nse-quant",
            attested_authority_id="gov-root-1",
            signature_hex=att_sig,
        ),
        verification_key=key,
    )
    assert result["authenticated"] is False
    assert result["reason"] == "NAMESPACE_OR_AUTHORITY_MISMATCH"


def test_authority_mismatch_refused():
    key, claim_sig, att_sig = _key_and_signatures(
        "nse-quant", "gov-root-1", claim_authority_id="gov-root-2"
    )
    result = authenticate_governance_authority(
        authority_claim=dict(
            namespace="nse-quant", authority_id="gov-root-2", signature_hex=claim_sig
        ),
        attestation=dict(
            attested_namespace="nse-quant",
            attested_authority_id="gov-root-1",
            signature_hex=att_sig,
        ),
        verification_key=key,
    )
    assert result["authenticated"] is False
    assert result["reason"] == "NAMESPACE_OR_AUTHORITY_MISMATCH"


def test_invalid_claim_signature_refused():
    key, _, att_sig = _key_and_signatures("nse-quant", "gov-root-1")
    result = authenticate_governance_authority(
        authority_claim=dict(
            namespace="nse-quant", authority_id="gov-root-1", signature_hex="00" * 64
        ),
        attestation=dict(
            attested_namespace="nse-quant",
            attested_authority_id="gov-root-1",
            signature_hex=att_sig,
        ),
        verification_key=key,
    )
    assert result["authenticated"] is False
    assert result["reason"] == "SIGNATURE_INVALID"


def test_missing_namespace_refused():
    key, claim_sig, att_sig = _key_and_signatures("nse-quant", "gov-root-1")
    result = authenticate_governance_authority(
        authority_claim=dict(authority_id="gov-root-1", signature_hex=claim_sig),
        attestation=dict(
            attested_namespace="nse-quant",
            attested_authority_id="gov-root-1",
            signature_hex=att_sig,
        ),
        verification_key=key,
    )
    assert result["authenticated"] is False
    assert result["reason"] == "NAMESPACE_REQUIRED"


def test_invalid_key_refused():
    result = authenticate_governance_authority(
        authority_claim=dict(
            namespace="nse-quant", authority_id="gov-root-1", signature_hex="00" * 128
        ),
        attestation=dict(
            attested_namespace="nse-quant",
            attested_authority_id="gov-root-1",
            signature_hex="00" * 128,
        ),
        verification_key=b"short",
    )
    assert result["authenticated"] is False
    assert result["reason"] == "VERIFICATION_KEY_INVALID"
