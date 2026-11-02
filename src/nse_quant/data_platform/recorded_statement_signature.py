"""Bind caller-supplied detached proof to freshly revalidated recorded content."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from nse_quant.data_platform.identity_statement_reader import RecordedStatementContent
    from nse_quant.data_platform.statement_signature import SignatureEvidence
    from nse_quant.data_platform.underlying_assertion import UnderlyingAssertionRequest

VERSION = "recorded-statement-signature-binding@1"


def check_payload_pin(payload: bytes, expected_sha256: str) -> str:
    """Bound exact original bytes before native work. No inferred format or authority."""
    if type(payload) is not bytes or not 0 < len(payload) <= 1048576:
        raise ValueError("BOUNDED_ORIGINAL_STATEMENT_BYTES_REQUIRED")
    if (
        not isinstance(expected_sha256, str)
        or re.fullmatch(r"[a-f0-9]{64}", expected_sha256) is None
    ):
        raise ValueError("EXACT_STATEMENT_PAYLOAD_SHA256_REQUIRED")
    actual = hashlib.sha256(payload).hexdigest()
    if actual != expected_sha256:
        raise ValueError("STATEMENT_SIGNATURE_PAYLOAD_PIN_MISMATCH")
    return actual


@dataclass(frozen=True)
class RecordedStatementSignature:
    version: str
    assertion_id: str
    status: str
    reason_codes: tuple[str, ...]
    content_before: RecordedStatementContent
    content_after: RecordedStatementContent | None = None
    signature: SignatureEvidence | None = None
    recorded_payload_signature_bound: bool = False
    evidence_fingerprint: str | None = None
    issuer_authenticated: bool = False
    namespace_authority_verified: bool = False
    identity_verified: bool = False
    canonical_underlying_id: None = None
    authorized_revocation_asserted: bool = False
    availability_evidence_verified: bool = False
    historical_validity_asserted: bool = False
    decision_eligibility_asserted: bool = False
    atomic_cross_database_snapshot_asserted: bool = False
    signature_acquisition_provenance_verified: bool = False


def inspect_recorded_statement_signature(
    registry: Any,
    bronze: Any,
    *,
    assertion_id: str,
    request: UnderlyingAssertionRequest,
    record_id: str,
    original_plan: bytes,
    expected_plan_sha256: str,
    payload: bytes,
    signature: bytes,
    public_key: bytes,
    expected_public_key_sha256: str,
) -> RecordedStatementSignature:
    """Read-only composition. Detached signature/key acquisition remains unchecked.

    payload is caller supplied but must match the exact recorded payload SHA256,
    then pass the same exact content/span expectations locally. Full native gates
    bracket verification; all changes observed require review, never old-good fallback.
    """
    from nse_quant.data_platform import identity_statement_reader as native
    from nse_quant.data_platform import statement_signature as crypto
    from nse_quant.data_platform import underlying_assertion as kernel
    from nse_quant.data_platform.identity_statement_document import (
        StatementExpectation,
        canonical,
        match_statement_content,
        pin,
        sha,
    )

    if native.VERSION != "recorded-identity-statement-content@1" or (
        crypto.VERSION != "pinned-statement-ed25519@1"
    ):
        raise ValueError("UNSUPPORTED_RECORDED_SIGNATURE_DEPENDENCY_VERSION")
    if type(request) is not kernel.UnderlyingAssertionRequest or not pin(assertion_id):
        raise ValueError("EXACT_TYPED_RECORDED_SIGNATURE_REQUEST_REQUIRED")
    checked = kernel.UnderlyingAssertionRequest(**asdict(request))
    check_payload_pin(payload, checked.evidence_payload_hash)

    def observe() -> native.RecordedStatementContent:
        return native.inspect_recorded_statement_content(
            registry,
            bronze,
            assertion_id=assertion_id,
            request=checked,
            record_id=record_id,
            original_plan=original_plan,
            expected_plan_sha256=expected_plan_sha256,
        )

    def complete(value: native.RecordedStatementContent) -> bool:
        return (
            type(value) is native.RecordedStatementContent
            and value.version == native.VERSION
            and value.assertion_id == assertion_id
            and value.status == "matched_untrusted_statement_support"
            and value.statement_content_matched is True
            and value.exact_record_span_verified is True
            and value.jsonl_derivation_verified is True
            and pin(value.evidence_fingerprint)
            and value.canonical_underlying_id is None
            and value.content is not None
            and value.content.record_id == record_id
            and value.content.payload_sha256 == checked.evidence_payload_hash
            and all(
                flag is False
                for flag in (
                    value.issuer_authenticated,
                    value.identity_verified,
                    value.authorized_revocation_asserted,
                    value.availability_evidence_verified,
                    value.historical_validity_asserted,
                    value.decision_eligibility_asserted,
                    value.atomic_cross_database_snapshot_asserted,
                )
            )
        )

    before = observe()
    if not complete(before):
        return RecordedStatementSignature(
            VERSION,
            assertion_id,
            "review_required",
            ("RECORDED_CONTENT_NOT_COMPLETE_BEFORE_SIGNATURE",),
            before,
        )
    expected = StatementExpectation(
        record_id,
        checked.namespace,
        checked.external_id,
        checked.asset_kind,
        checked.asserted_issuer,
        checked.assertion,
        checked.evidence_byte_start,
        checked.evidence_byte_end,
        checked.evidence_payload_hash,
        checked.evidence_fragment_sha256,
    )
    content = match_statement_content(payload, expected=expected)
    proof = crypto.verify_pinned_statement_signature(
        payload,
        signature=signature,
        public_key=public_key,
        expected_public_key_sha256=expected_public_key_sha256,
    )
    after = observe()
    reasons: list[str] = []
    if not complete(after) or canonical(asdict(before)) != canonical(asdict(after)):
        reasons.append("RECORDED_CONTENT_CHANGED_OR_INCOMPLETE_AFTER_SIGNATURE")
    if before.content != content or after.content != content:
        reasons.append("SIGNATURE_PAYLOAD_CONTENT_VIEW_MISMATCH")
    if not proof.cryptographic_signature_verified:
        reasons.append("RECORDED_PAYLOAD_SIGNATURE_NOT_VALID_UNDER_PINNED_KEY")
    if reasons:
        return RecordedStatementSignature(
            VERSION,
            assertion_id,
            "review_required",
            tuple(reasons),
            before,
            after,
            proof,
        )
    fingerprint = sha(
        canonical(
            [
                VERSION,
                assertion_id,
                record_id,
                asdict(before),
                asdict(after),
                asdict(proof),
            ]
        ).encode()
    )
    return RecordedStatementSignature(
        VERSION,
        assertion_id,
        "recorded_payload_signature_bound_under_pinned_key",
        ("EXACT_RECORDED_PAYLOAD_SIGNATURE_BOUND",),
        before,
        after,
        proof,
        True,
        fingerprint,
    )
