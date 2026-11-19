"""Signed exact-scope policy constraints; not independently established authority."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

VERSION = "statement-key-scope-policy@1"
DOMAIN = b"nse-quant/statement-key-scope-policy/ed25519/v1\x00"
MAX_BYTES = 65536
MAX_GRANTS = 128
MAX_DENIED_KEYS = 128


class ScopePolicyRejected(ValueError):
    """Invalid input/document, using fixed diagnostic codes only."""


def _pin(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _id(value: object, limit: int) -> bool:
    return (
        isinstance(value, str)
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0," + str(limit - 1) + "}", value)
        is not None
    )


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise ScopePolicyRejected("SCOPE_POLICY_DUPLICATE_KEY")
        result[key] = value
    return result


def _invalid(_value: str) -> Any:
    raise ScopePolicyRejected("SCOPE_POLICY_NONFINITE_JSON")


def policy_signing_message(raw: bytes) -> bytes:
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_BYTES:
        raise ScopePolicyRejected("SCOPE_POLICY_BYTE_LIMIT")
    return DOMAIN + len(raw).to_bytes(8, "big") + raw


@dataclass(frozen=True)
class ScopeQuery:
    namespace: str
    external_id: str
    asset_kind: str
    asserted_issuer: str
    assertion: str
    signer_key_sha256: str

    def __post_init__(self) -> None:
        if (
            not _id(self.namespace, 64)
            or not _id(self.external_id, 256)
            or not _id(self.asserted_issuer, 128)
            or not _pin(self.signer_key_sha256)
            or self.asset_kind not in ("INDEX", "EQUITY")
            or self.assertion not in ("ASSERTED", "DISPUTED", "WITHDRAWN")
        ):
            raise ScopePolicyRejected("EXACT_SCOPE_QUERY_REQUIRED")


@dataclass(frozen=True)
class ScopeAssessment:
    version: str
    status: str
    reason_codes: tuple[str, ...]
    policy_sha256: str
    governance_key_sha256: str
    policy_id: str
    sequence: int
    matched_grant_ids: tuple[str, ...]
    governance_signature_verified: bool
    supplied_policy_permits_scope: bool = False
    policy_authority_authenticated: bool = False
    policy_currentness_verified: bool = False
    issuer_authenticated: bool = False
    namespace_authority_verified: bool = False
    identity_verified: bool = False
    authorized_revocation_asserted: bool = False
    availability_evidence_verified: bool = False
    historical_validity_asserted: bool = False
    decision_eligibility_asserted: bool = False
    canonical_underlying_id: None = None


def assess_signed_scope_policy(
    raw: bytes,
    *,
    policy_signature: bytes,
    governance_public_key: bytes,
    expected_policy_sha256: str,
    expected_governance_key_sha256: str,
    query: ScopeQuery,
) -> ScopeAssessment:
    """Evaluate a complete pinned policy, not a caller-created decoded-policy DTO.

    A governance key AND its matching pin can be attacker chosen. This API proves
    signature and policy constraints only, never independently authenticates authority.
    """
    message = policy_signing_message(raw)
    if (
        type(query) is not ScopeQuery
        or not _pin(expected_policy_sha256)
        or not _pin(expected_governance_key_sha256)
        or type(governance_public_key) is not bytes
        or len(governance_public_key) != 32
        or type(policy_signature) is not bytes
        or len(policy_signature) != 64
    ):
        raise ScopePolicyRejected("EXPLICIT_POLICY_PINS_KEY_SIGNATURE_AND_QUERY_REQUIRED")
    query = ScopeQuery(**query.__dict__)
    digest = hashlib.sha256(raw).hexdigest()
    key_digest = hashlib.sha256(governance_public_key).hexdigest()
    if digest != expected_policy_sha256 or key_digest != expected_governance_key_sha256:
        raise ScopePolicyRejected("SCOPE_POLICY_OR_GOVERNANCE_KEY_PIN_MISMATCH")
    try:
        Ed25519PublicKey.from_public_bytes(governance_public_key).verify(policy_signature, message)
    except InvalidSignature:
        raise ScopePolicyRejected("SCOPE_POLICY_SIGNATURE_INVALID") from None
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_invalid)
        if (
            not isinstance(value, dict)
            or set(value) != {"schema", "policy_id", "sequence", "grants", "denied_keys"}
            or value["schema"] != VERSION
            or _canonical(value) != raw
            or not _id(value["policy_id"], 64)
            or type(value["sequence"]) is not int
            or not 1 <= value["sequence"] <= 2147483647
        ):
            raise ScopePolicyRejected("SCOPE_POLICY_SCHEMA_INVALID")
        grants, denied = value["grants"], value["denied_keys"]
        if (
            not isinstance(grants, list)
            or len(grants) > MAX_GRANTS
            or not isinstance(denied, list)
            or len(denied) > MAX_DENIED_KEYS
            or any(not _pin(key) for key in denied)
            or len(set(denied)) != len(denied)
        ):
            raise ScopePolicyRejected("SCOPE_POLICY_CAPACITY_OR_DENIAL_INVALID")
        seen: set[str] = set()
        matches: list[str] = []
        for grant in grants:
            if (
                not isinstance(grant, dict)
                or set(grant)
                != {
                    "grant_id",
                    "namespace",
                    "external_id",
                    "asset_kind",
                    "asserted_issuer",
                    "assertion",
                    "signer_key_sha256",
                }
                or not _id(grant["grant_id"], 64)
                or grant["grant_id"] in seen
            ):
                raise ScopePolicyRejected("SCOPE_POLICY_GRANT_INVALID_OR_DUPLICATE")
            seen.add(grant["grant_id"])
            scope = ScopeQuery(**{key: item for key, item in grant.items() if key != "grant_id"})
            if scope == query:
                matches.append(grant["grant_id"])
    except ScopePolicyRejected:
        raise
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        raise ScopePolicyRejected("SCOPE_POLICY_MALFORMED") from None
    if query.signer_key_sha256 in denied:
        status, reasons = "denied_under_supplied_policy", ("SIGNER_KEY_EXPLICITLY_DENIED",)
    elif len(matches) > 1:
        status, reasons = "review_required", ("MULTIPLE_EXACT_GRANTS_REQUIRE_RESOLUTION",)
    elif not matches:
        status, reasons = "denied_under_supplied_policy", ("NO_EXACT_SCOPE_GRANT",)
    else:
        status, reasons = "permitted_under_supplied_policy", ("EXACT_SCOPE_GRANT_MATCHED",)
    return ScopeAssessment(
        VERSION,
        status,
        reasons,
        digest,
        key_digest,
        value["policy_id"],
        value["sequence"],
        tuple(sorted(matches)),
        True,
        status == "permitted_under_supplied_policy",
    )
