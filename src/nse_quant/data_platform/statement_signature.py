"""Detached Ed25519 proof of pinned-key possession; never issuer authorization."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

VERSION = "pinned-statement-ed25519@1"
DOMAIN = b"nse-quant/underlying-statement-signature/ed25519/v1\x00"
MAX_PAYLOAD_BYTES = 1048576


@dataclass(frozen=True)
class SignatureEvidence:
    version: str
    status: str
    reason_codes: tuple[str, ...]
    payload_sha256: str
    public_key_sha256: str
    signature_sha256: str
    cryptographic_signature_verified: bool
    issuer_authenticated: bool = False
    namespace_authority_verified: bool = False
    identity_verified: bool = False
    authorized_revocation_asserted: bool = False
    availability_evidence_verified: bool = False
    historical_validity_asserted: bool = False
    decision_eligibility_asserted: bool = False
    canonical_underlying_id: None = None


def signing_message(payload: bytes) -> bytes:
    """Profile framing only. Not a signing service or a canonicalizing encoder."""
    if type(payload) is not bytes or not 0 < len(payload) <= MAX_PAYLOAD_BYTES:
        raise ValueError("SIGNATURE_PAYLOAD_BYTES_REQUIRED_WITHIN_BOUND")
    return DOMAIN + len(payload).to_bytes(8, "big") + payload


def verify_pinned_statement_signature(
    payload: bytes,
    *,
    signature: bytes,
    public_key: bytes,
    expected_public_key_sha256: str,
) -> SignatureEvidence:
    """Verify opaque ORIGINAL bytes; no document parsing, trust lookup or I/O.

    The key pin must be independently supplied by the caller, never discovered
    from the document. Matching that pin is not proof the caller trusts a key
    legitimately, nor authorization of any namespace, claim or revocation.
    """
    message = signing_message(payload)
    if type(signature) is not bytes or len(signature) != 64:
        raise ValueError("EXACT_64_BYTE_ED25519_SIGNATURE_REQUIRED")
    if type(public_key) is not bytes or len(public_key) != 32:
        raise ValueError("EXACT_32_BYTE_ED25519_PUBLIC_KEY_REQUIRED")
    if (
        not isinstance(expected_public_key_sha256, str)
        or re.fullmatch(r"[a-f0-9]{64}", expected_public_key_sha256) is None
    ):
        raise ValueError("EXPLICIT_LOWERCASE_PUBLIC_KEY_SHA256_REQUIRED")
    payload_hash = hashlib.sha256(payload).hexdigest()
    key_hash = hashlib.sha256(public_key).hexdigest()
    signature_hash = hashlib.sha256(signature).hexdigest()
    if key_hash != expected_public_key_sha256:
        return SignatureEvidence(
            VERSION,
            "review_required",
            ("PUBLIC_KEY_PIN_MISMATCH",),
            payload_hash,
            key_hash,
            signature_hash,
            False,
        )
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(signature, message)
    except InvalidSignature:
        return SignatureEvidence(
            VERSION,
            "review_required",
            ("DETACHED_SIGNATURE_INVALID",),
            payload_hash,
            key_hash,
            signature_hash,
            False,
        )
    return SignatureEvidence(
        VERSION,
        "valid_signature_under_pinned_key",
        ("PINNED_KEY_SIGNATURE_VALID",),
        payload_hash,
        key_hash,
        signature_hash,
        True,
    )
