"""Role-separated review evidence, never a self-bootstrapped governance authority."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

VERSION = "delegation-review-evidence@1"
INTERNAL = "INTERNAL_RESEARCH"
EXTERNAL = "EXTERNAL_ISSUER"
SCHEMAS = {
    INTERNAL: "internal-research-delegation@1",
    EXTERNAL: "external-issuer-delegation-claim@1",
}
ROLES = {
    INTERNAL: ("RESEARCH_OWNER", "RISK_REVIEWER"),
    EXTERNAL: ("AUTHORITY_REVIEWER", "INDEPENDENT_REVIEWER"),
}
DOMAIN = b"nse-quant/delegation-review/ed25519/v1\x00"
MAX_BYTES = 16384


class DelegationReviewRejected(ValueError):
    """Fixed-code shape/cryptographic rejection, not issuer rejection."""


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
            raise DelegationReviewRejected("DELEGATION_DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _invalid(_value: str) -> Any:
    raise DelegationReviewRejected("DELEGATION_NONFINITE_JSON")


@dataclass(frozen=True)
class DelegationTarget:
    namespace: str
    asset_kind: str
    policy_id: str
    governance_key_sha256: str
    checkpoint_id: str
    checkpoint_history_fingerprint: str

    def __post_init__(self) -> None:
        if (
            not _id(self.namespace, 64)
            or not _id(self.policy_id, 64)
            or self.asset_kind not in ("INDEX", "EQUITY")
            or not all(
                _pin(x)
                for x in (
                    self.governance_key_sha256,
                    self.checkpoint_id,
                    self.checkpoint_history_fingerprint,
                )
            )
        ):
            raise DelegationReviewRejected("EXACT_DELEGATION_TARGET_REQUIRED")


@dataclass(frozen=True)
class ReviewerProof:
    role: str
    public_key: bytes
    signature: bytes
    expected_public_key_sha256: str


def review_signing_message(raw: bytes, role: str) -> bytes:
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_BYTES:
        raise DelegationReviewRejected("DELEGATION_ORIGINAL_BYTE_LIMIT")
    if role not in ROLES[INTERNAL] + ROLES[EXTERNAL]:
        raise DelegationReviewRejected("DELEGATION_REVIEW_ROLE_NOT_SUPPORTED")
    label = role.encode("ascii")
    return DOMAIN + len(label).to_bytes(2, "big") + label + len(raw).to_bytes(8, "big") + raw


@dataclass(frozen=True)
class DelegationReview:
    version: str
    model: str
    status: str
    reason_codes: tuple[str, ...]
    document_sha256: str
    delegation_id: str
    target: DelegationTarget
    reviewer_key_sha256s: tuple[str, ...]
    approval_quorum_signatures_verified: bool
    internal_review_constraints_satisfied: bool = False
    evidence_fingerprint: str | None = None
    supporting_bronze_refs_checked: bool = False
    reviewer_identities_authenticated: bool = False
    independent_humans_verified: bool = False
    internal_authorization_asserted: bool = False
    external_issuer_authority_verified: bool = False
    policy_authority_authenticated: bool = False
    namespace_authority_verified: bool = False
    issuer_authenticated: bool = False
    identity_verified: bool = False
    authorized_revocation_asserted: bool = False
    decision_eligibility_asserted: bool = False
    canonical_underlying_id: None = None


def assess_delegation_review(
    raw: bytes,
    *,
    expected_document_sha256: str,
    expected_model: str,
    expected_target: DelegationTarget,
    proofs: tuple[ReviewerProof, ...],
) -> DelegationReview:
    """No roots are registered; pins supplied here are external caller expectations.

    Positive internal evidence means role-separated signatures and exact constraints,
    NOT an independently authenticated organizational approval or operative authority.
    External model is explicitly blocked regardless of signature success.
    """
    if (
        not isinstance(expected_model, str)
        or expected_model not in SCHEMAS
        or type(expected_target) is not DelegationTarget
        or not _pin(expected_document_sha256)
    ):
        raise DelegationReviewRejected("EXPLICIT_DELEGATION_MODEL_TARGET_AND_PIN_REQUIRED")
    expected_target = DelegationTarget(**asdict(expected_target))
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_BYTES:
        raise DelegationReviewRejected("DELEGATION_ORIGINAL_BYTE_LIMIT")
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected_document_sha256:
        raise DelegationReviewRejected("DELEGATION_DOCUMENT_PIN_MISMATCH")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_invalid)
        common = {
            "schema",
            "delegation_id",
            "target",
            "capability",
            "evidence_refs",
            "statement_kind",
        }
        extras = (
            {"organization_ref"}
            if expected_model == INTERNAL
            else {"claimed_issuer_ref", "verification_method"}
        )
        if (
            not isinstance(value, dict)
            or set(value) != common | extras
            or value["schema"] != SCHEMAS[expected_model]
            or _canonical(value) != raw
            or not _id(value["delegation_id"], 64)
            or not isinstance(value["target"], dict)
            or value["capability"] != "SIGN_RESEARCH_SCOPE_POLICY"
            or value["statement_kind"] not in ("APPROVE", "DISPUTE", "WITHDRAW")
        ):
            raise DelegationReviewRejected("DELEGATION_SCHEMA_OR_CAPABILITY_INVALID")
        target = DelegationTarget(**value["target"])
        if expected_model == INTERNAL:
            if not _id(value["organization_ref"], 128):
                raise DelegationReviewRejected("DELEGATION_ORGANIZATION_LABEL_INVALID")
        elif (
            not _id(value["claimed_issuer_ref"], 128)
            or value["verification_method"] != "INDEPENDENT_EXTERNAL_REVIEW_REQUIRED"
        ):
            raise DelegationReviewRejected("DELEGATION_EXTERNAL_METHOD_NOT_SUPPORTED")
        refs = value["evidence_refs"]
        if not isinstance(refs, list) or not 1 <= len(refs) <= 8:
            raise DelegationReviewRejected("DELEGATION_EVIDENCE_REFERENCE_LIMIT")
        seen: set[str] = set()
        for ref in refs:
            if (
                not isinstance(ref, dict)
                or set(ref)
                != {
                    "capture_event_id",
                    "envelope_hash",
                    "payload_hash",
                    "byte_start",
                    "byte_end",
                    "fragment_sha256",
                }
                or any(
                    not _pin(ref[key])
                    for key in (
                        "capture_event_id",
                        "envelope_hash",
                        "payload_hash",
                        "fragment_sha256",
                    )
                )
                or type(ref["byte_start"]) is not int
                or type(ref["byte_end"]) is not int
                or not 0 <= ref["byte_start"] < ref["byte_end"] <= 1048576
            ):
                raise DelegationReviewRejected("DELEGATION_EVIDENCE_REFERENCE_INVALID")
            encoded = _canonical(ref).decode()
            if encoded in seen:
                raise DelegationReviewRejected("DELEGATION_DUPLICATE_EVIDENCE_REFERENCE")
            seen.add(encoded)
    except DelegationReviewRejected:
        raise
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError):
        raise DelegationReviewRejected("DELEGATION_DOCUMENT_MALFORMED") from None
    if type(proofs) is not tuple or len(proofs) != 2:
        raise DelegationReviewRejected("EXACT_TWO_ROLE_REVIEW_PROOFS_REQUIRED")
    keys: dict[str, str] = {}
    signatures: dict[str, str] = {}
    for proof in proofs:
        if (
            type(proof) is not ReviewerProof
            or proof.role not in ROLES[expected_model]
            or proof.role in keys
            or type(proof.public_key) is not bytes
            or len(proof.public_key) != 32
            or type(proof.signature) is not bytes
            or len(proof.signature) != 64
            or not _pin(proof.expected_public_key_sha256)
        ):
            raise DelegationReviewRejected("DELEGATION_REVIEW_PROOF_SHAPE_OR_ROLE_INVALID")
        key = hashlib.sha256(proof.public_key).hexdigest()
        if key != proof.expected_public_key_sha256:
            raise DelegationReviewRejected("DELEGATION_REVIEW_KEY_PIN_MISMATCH")
        if key == target.governance_key_sha256 or key in keys.values():
            raise DelegationReviewRejected("DELEGATION_SELF_OR_DUPLICATE_KEY_APPROVAL")
        try:
            Ed25519PublicKey.from_public_bytes(proof.public_key).verify(
                proof.signature, review_signing_message(raw, proof.role)
            )
        except InvalidSignature:
            raise DelegationReviewRejected("DELEGATION_ROLE_SIGNATURE_INVALID") from None
        keys[proof.role] = key
        signatures[proof.role] = hashlib.sha256(proof.signature).hexdigest()
    reasons: tuple[str, ...]
    if value["statement_kind"] != "APPROVE":
        status, reasons = "review_required", ("DELEGATION_DISPUTE_OR_WITHDRAWAL_REQUIRES_REVIEW",)
    elif target != expected_target:
        status, reasons = "review_required", ("DELEGATION_EXACT_TARGET_MISMATCH",)
    elif expected_model == EXTERNAL:
        status, reasons = "review_required", ("INDEPENDENT_EXTERNAL_AUTHORITY_VERIFIER_REQUIRED",)
    else:
        status, reasons = "matched_internal_review_evidence", ("EXACT_TWO_KEY_REVIEW_EVIDENCE",)
    matched = status == "matched_internal_review_evidence"
    fingerprint = hashlib.sha256(
        _canonical(
            [
                VERSION,
                expected_model,
                digest,
                asdict(expected_target),
                keys,
                signatures,
                reasons,
            ]
        )
    ).hexdigest()
    return DelegationReview(
        VERSION,
        expected_model,
        status,
        reasons,
        digest,
        value["delegation_id"],
        target,
        tuple(keys[role] for role in ROLES[expected_model]),
        True,
        matched,
        fingerprint,
    )


@dataclass(frozen=True)
class DelegationInput:
    document: bytes
    expected_sha256: str
    proofs: tuple[ReviewerProof, ...]


@dataclass(frozen=True)
class DelegationReviewSet:
    version: str
    status: str
    reason_codes: tuple[str, ...]
    observations: tuple[DelegationReview, ...]
    internal_review_constraints_satisfied: bool
    evidence_fingerprint: str
    supplied_set_completeness_asserted: bool = False
    policy_authority_authenticated: bool = False
    issuer_authenticated: bool = False
    authorized_revocation_asserted: bool = False
    decision_eligibility_asserted: bool = False


def assess_delegation_review_set(
    declarations: tuple[DelegationInput, ...],
    *,
    expected_model: str,
    expected_target: DelegationTarget,
) -> DelegationReviewSet:
    """All supplied declarations resolve before selection; no first/last preference.

    Not discovery of all real-world declarations. Exact duplicates are retained;
    distinct declarations or any negative/inconsistent result require review.
    """
    if type(declarations) is not tuple or not 1 <= len(declarations) <= 8:
        raise DelegationReviewRejected("BOUNDED_IMMUTABLE_DELEGATION_SET_REQUIRED")
    results: list[DelegationReview] = []
    for item in declarations:
        if type(item) is not DelegationInput:
            raise DelegationReviewRejected("TYPED_DELEGATION_INPUT_REQUIRED")
        results.append(
            assess_delegation_review(
                item.document,
                expected_document_sha256=item.expected_sha256,
                expected_model=expected_model,
                expected_target=expected_target,
                proofs=item.proofs,
            )
        )
    reasons: list[str] = []
    if len({item.document_sha256 for item in results}) != 1:
        reasons.append("MULTIPLE_DISTINCT_DELEGATIONS_REQUIRE_INDEPENDENT_RESOLUTION")
    if not all(item.internal_review_constraints_satisfied for item in results):
        reasons.append("DELEGATION_SET_CONTAINS_UNRESOLVED_OR_EXTERNAL_EVIDENCE")
    fingerprint = hashlib.sha256(
        _canonical(
            [
                VERSION,
                expected_model,
                asdict(expected_target),
                [asdict(item) for item in results],
            ]
        )
    ).hexdigest()
    return DelegationReviewSet(
        VERSION,
        "matched_internal_review_set" if not reasons else "review_required",
        tuple(reasons) if reasons else ("EXACT_INTERNAL_REVIEW_SET_MATCHED",),
        tuple(results),
        not reasons,
        fingerprint,
    )
