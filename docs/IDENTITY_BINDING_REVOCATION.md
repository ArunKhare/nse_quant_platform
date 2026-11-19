# Identity binding and authorized revocation

`validate_identity_binding` validates an identity binding (underlying -> derivative) and checks authorized revocation status without synthesizing identity or granting decision eligibility.

## Contract

- Input: binding dict (underlying, derivative, signature_hex), revocation_record (optional dict with revoked, signature_hex), verification_key (32 bytes).
- Output: dict with valid, reason, underlying, derivative, revoked.
- Safety: never synthesizes identity, never grants decision eligibility, never enables live trading.

## Rules

- Valid only when binding signature verifies AND revocation is absent or explicitly authorized.
- Refuses invalid signature, missing underlying/derivative, invalid key.
- Addresses gate 2 from docs/CURRENT_NATIVE_STATUS.md.
