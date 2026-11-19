"""Authoritative identity binding and authorized revocation check.

Validates an identity binding (underlying -> derivative) and checks authorized
revocation status without synthesizing identity or granting decision eligibility.
Addresses gate 2 from docs/CURRENT_NATIVE_STATUS.md.
"""

from __future__ import annotations

from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


def validate_identity_binding(
    *,
    binding: dict[str, Any],
    revocation_record: dict[str, Any] | None,
    verification_key: bytes,
) -> dict[str, Any]:
    """Validate identity binding and authorized revocation status."""
    if type(binding) is not dict:
        return dict(valid=False, reason="BINDING_OBJECT_REQUIRED")
    if type(verification_key) is not bytes or len(verification_key) != 32:
        return dict(valid=False, reason="VERIFICATION_KEY_INVALID")

    underlying = binding.get("underlying")
    derivative = binding.get("derivative")
    signature_hex = binding.get("signature_hex")
    if type(underlying) is not str or not underlying:
        return dict(valid=False, reason="UNDERLYING_REQUIRED")
    if type(derivative) is not str or not derivative:
        return dict(valid=False, reason="DERIVATIVE_REQUIRED")
    if type(signature_hex) is not str or len(signature_hex) != 128:
        return dict(valid=False, reason="SIGNATURE_SHAPE_INVALID")

    try:
        signature = bytes.fromhex(signature_hex)
    except ValueError:
        return dict(valid=False, reason="SIGNATURE_HEX_INVALID")

    message = f"{underlying}->{derivative}".encode()
    try:
        Ed25519PublicKey.from_public_bytes(verification_key).verify(signature, message)
    except InvalidSignature:
        return dict(valid=False, reason="SIGNATURE_INVALID")

    revoked = False
    if revocation_record is not None:
        if type(revocation_record) is not dict:
            return dict(valid=False, reason="REVOCATION_OBJECT_INVALID")
        revoked = revocation_record.get("revoked", False) is True
        rev_sig = revocation_record.get("signature_hex")
        if type(rev_sig) is not str or len(rev_sig) != 128:
            return dict(valid=False, reason="REVOCATION_SIGNATURE_SHAPE_INVALID")
        try:
            rev_signature = bytes.fromhex(rev_sig)
        except ValueError:
            return dict(valid=False, reason="REVOCATION_SIGNATURE_HEX_INVALID")
        rev_message = f"REVOKE:{underlying}->{derivative}".encode()
        try:
            Ed25519PublicKey.from_public_bytes(verification_key).verify(rev_signature, rev_message)
        except InvalidSignature:
            return dict(valid=False, reason="REVOCATION_SIGNATURE_INVALID")

    return dict(
        valid=not revoked,
        reason="BINDING_VALID" if not revoked else "BINDING_REVOKED",
        underlying=underlying,
        derivative=derivative,
        revoked=revoked,
    )
