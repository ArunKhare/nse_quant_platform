# Independent time-evidence cross-check

`cross_check_declared_time` cross-checks a declared time against an independently-supplied, separately-signed time attestation without synthesizing truth.

## Contract

- Input: declared_time (str), attestation dict (attested_time, signature_hex), verification_key (32 bytes).
- Output: dict with consistent, reason, declared_time, attested_time.
- Safety: never synthesizes truth, never grants decision eligibility, never enables live trading.

## Rules

- Consistent only when declared_time == attested_time AND signature verifies.
- Refuses invalid signature, missing attested_time, invalid key.
- Complements signed_temporal_evidence.py (which validates declared intervals but flags independent_time_evidence_verified as False).
