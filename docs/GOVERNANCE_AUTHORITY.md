# Governance/namespace authority authentication

`authenticate_governance_authority` validates a governance/namespace authority claim against an independently-supplied, separately-signed authority attestation without synthesizing authority or granting decision eligibility.

## Contract

- Input: authority_claim dict (namespace, authority_id, signature_hex), attestation dict (attested_namespace, attested_authority_id, signature_hex), verification_key (32 bytes).
- Output: dict with authenticated, reason, namespace, authority_id.
- Safety: never synthesizes authority, never grants decision eligibility, never enables live trading.

## Rules

- Authenticated only when namespace and authority_id match AND both signatures verify.
- Refuses invalid signature, missing namespace/authority_id, invalid key.
- Addresses gate 1 from docs/CURRENT_NATIVE_STATUS.md.
