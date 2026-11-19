"""Governance/namespace authority authentication.

Validates a governance/namespace authority claim against an independently-supplied,
separately-signed authority attestation without synthesizing authority or granting
decision eligibility. Addresses gate 1 from docs/CURRENT_NATIVE_STATUS.md.
"""

from __future__ import annotations

from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


def authenticate_governance_authority(
    *,
    authority_claim: dict[str, Any],
    attestation: dict[str, Any],
    verification_key: bytes,
) -> dict[str, Any]:
    """Authenticate a governance/namespace authority claim against an attestation."""
    if type(authority_claim) is not dict:
        return dict(authenticated=False, reason="AUTHORITY_CLAIM_OBJECT_REQUIRED")
    if type(attestation) is not dict:
        return dict(authenticated=False, reason="ATTESTATION_OBJECT_REQUIRED")
    if type(verification_key) is not bytes or len(verification_key) != 32:
        return dict(authenticated=False, reason="VERIFICATION_KEY_INVALID")

    namespace = authority_claim.get("namespace")
    authority_id = authority_claim.get("authority_id")
    claim_sig_hex = authority_claim.get("signature_hex")
    if type(namespace) is not str or not namespace:
        return dict(authenticated=False, reason="NAMESPACE_REQUIRED")
    if type(authority_id) is not str or not authority_id:
        return dict(authenticated=False, reason="AUTHORITY_ID_REQUIRED")
    if type(claim_sig_hex) is not str or len(claim_sig_hex) != 128:
        return dict(authenticated=False, reason="CLAIM_SIGNATURE_SHAPE_INVALID")

    attested_namespace = attestation.get("attested_namespace")
    attested_authority_id = attestation.get("attested_authority_id")
    att_sig_hex = attestation.get("signature_hex")
    if type(attested_namespace) is not str or not attested_namespace:
        return dict(authenticated=False, reason="ATTESTED_NAMESPACE_REQUIRED")
    if type(attested_authority_id) is not str or not attested_authority_id:
        return dict(authenticated=False, reason="ATTESTED_AUTHORITY_ID_REQUIRED")
    if type(att_sig_hex) is not str or len(att_sig_hex) != 128:
        return dict(authenticated=False, reason="ATTESTATION_SIGNATURE_SHAPE_INVALID")

    try:
        claim_signature = bytes.fromhex(claim_sig_hex)
        att_signature = bytes.fromhex(att_sig_hex)
    except ValueError:
        return dict(authenticated=False, reason="SIGNATURE_HEX_INVALID")

    claim_message = f"AUTHORITY:{namespace}:{authority_id}".encode()
    att_message = f"ATTEST:{attested_namespace}:{attested_authority_id}".encode()
    try:
        Ed25519PublicKey.from_public_bytes(verification_key).verify(claim_signature, claim_message)
        Ed25519PublicKey.from_public_bytes(verification_key).verify(att_signature, att_message)
    except InvalidSignature:
        return dict(authenticated=False, reason="SIGNATURE_INVALID")

    namespace_match = namespace == attested_namespace
    authority_match = authority_id == attested_authority_id
    authenticated = namespace_match and authority_match
    return dict(
        authenticated=authenticated,
        reason=("AUTHORITY_AUTHENTICATED" if authenticated else "NAMESPACE_OR_AUTHORITY_MISMATCH"),
        namespace=namespace,
        authority_id=authority_id,
    )
