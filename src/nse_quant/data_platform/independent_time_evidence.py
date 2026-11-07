"""Independent time-evidence cross-check.

Cross-checks a declared time against an independently-supplied, separately-signed
time attestation without synthesizing truth. Addresses the "independently
evidenced" part of gate 3 from docs/CURRENT_NATIVE_STATUS.md, complementing
signed_temporal_evidence.py (which validates declared intervals but explicitly
flags independent_time_evidence_verified as False).
"""

from __future__ import annotations

from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


def cross_check_declared_time(
    *,
    declared_time: str,
    attestation: dict[str, Any],
    verification_key: bytes,
) -> dict[str, Any]:
    """Cross-check a declared time against an independently-signed attestation."""
    if type(declared_time) is not str or not declared_time:
        return dict(consistent=False, reason="DECLARED_TIME_REQUIRED")
    if type(attestation) is not dict:
        return dict(consistent=False, reason="ATTESTATION_OBJECT_REQUIRED")
    if type(verification_key) is not bytes or len(verification_key) != 32:
        return dict(consistent=False, reason="VERIFICATION_KEY_INVALID")

    attested_time = attestation.get("attested_time")
    signature_hex = attestation.get("signature_hex")
    if type(attested_time) is not str or not attested_time:
        return dict(consistent=False, reason="ATTESTED_TIME_REQUIRED")
    if type(signature_hex) is not str or len(signature_hex) != 128:
        return dict(consistent=False, reason="SIGNATURE_SHAPE_INVALID")

    try:
        signature = bytes.fromhex(signature_hex)
    except ValueError:
        return dict(consistent=False, reason="SIGNATURE_HEX_INVALID")

    message = attested_time.encode("utf-8")
    try:
        Ed25519PublicKey.from_public_bytes(verification_key).verify(signature, message)
    except InvalidSignature:
        return dict(consistent=False, reason="SIGNATURE_INVALID")

    consistent = declared_time == attested_time
    return dict(
        consistent=consistent,
        reason="DECLARED_MATCHES_INDEPENDENTLY_ATTESTED"
        if consistent
        else "DECLARED_MISMATCHES_INDEPENDENTLY_ATTESTED",
        declared_time=declared_time,
        attested_time=attested_time,
    )
