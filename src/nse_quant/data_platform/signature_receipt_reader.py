"""Native proof-artifact receipt linkage, not authenticated source acquisition."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from nse_quant.data_platform.signature_artifact import (
    PAYLOAD_FORMAT,
    SignatureArtifact,
    SignatureArtifactRejected,
    parse_signature_artifact,
)

if TYPE_CHECKING:
    from nse_quant.data_platform.bronze_jsonl_support_reader import JsonlSupportEvidence
    from nse_quant.data_platform.bronze_support_reader import BronzeSupportPin
    from nse_quant.data_platform.recorded_statement_signature import RecordedStatementSignature
    from nse_quant.data_platform.underlying_assertion import UnderlyingAssertionRequest

VERSION = "recorded-signature-receipt-linkage@1"


@dataclass(frozen=True)
class SignatureReceiptEvidence:
    version: str
    assertion_id: str
    status: str
    reason_codes: tuple[str, ...]
    proof_before: JsonlSupportEvidence
    proof_after: JsonlSupportEvidence | None = None
    binding_before: RecordedStatementSignature | None = None
    binding_after: RecordedStatementSignature | None = None
    artifact: SignatureArtifact | None = None
    proof_receipt_storage_linkage_verified: bool = False
    evidence_fingerprint: str | None = None
    signature_acquisition_provenance_verified: bool = False
    source_acquisition_authenticity_asserted: bool = False
    issuer_authenticated: bool = False
    namespace_authority_verified: bool = False
    identity_verified: bool = False
    canonical_underlying_id: None = None
    authorized_revocation_asserted: bool = False
    availability_evidence_verified: bool = False
    historical_validity_asserted: bool = False
    decision_eligibility_asserted: bool = False
    atomic_cross_database_snapshot_asserted: bool = False


def inspect_signature_receipt(
    registry: Any,
    bronze: Any,
    proof_bronze: Any,
    *,
    assertion_id: str,
    request: UnderlyingAssertionRequest,
    record_id: str,
    original_plan: bytes,
    expected_plan_sha256: str,
    payload: bytes,
    proof_support: BronzeSupportPin,
    proof_plan: bytes,
    expected_proof_plan_sha256: str,
    expected_public_key_sha256: str,
) -> SignatureReceiptEvidence:
    """Proof bytes are fetched from Bronze; no caller signature/key substitution.

    Explicit external key pin remains mandatory. Source acquisition truth stays
    unknown. Owned native connections, no outer transactions, no writes or opens.
    """
    from nse_quant.data_platform import bronze_jsonl_support_reader as jsonl
    from nse_quant.data_platform import bronze_support_reader as source
    from nse_quant.data_platform import recorded_statement_signature as binding
    from nse_quant.data_platform import underlying_assertion as kernel
    from nse_quant.data_platform.identity_statement_document import canonical, pin, sha

    if (
        jsonl.VERSION != "bronze-jsonl-support-consumer@1"
        or source.VERSION != "pinned-bronze-support-storage@1"
        or binding.VERSION != "recorded-statement-signature-binding@1"
    ):
        raise ValueError("UNSUPPORTED_SIGNATURE_RECEIPT_DEPENDENCY_VERSION")
    if type(proof_support) is not source.BronzeSupportPin:
        raise TypeError("EXACT_TYPED_SIGNATURE_PROOF_SUPPORT_REQUIRED")
    support = source.BronzeSupportPin(**asdict(proof_support))
    if type(request) is not kernel.UnderlyingAssertionRequest or not pin(assertion_id):
        raise ValueError("EXACT_TYPED_SIGNATURE_RECEIPT_TARGET_REQUIRED")
    checked = kernel.UnderlyingAssertionRequest(**asdict(request))
    if (
        support.byte_start != 0
        or support.byte_end > 4096
        or support.fragment_sha256 != support.payload_hash
    ):
        raise ValueError("SIGNATURE_PROOF_WHOLE_PAYLOAD_PIN_REQUIRED")

    def observe() -> jsonl.JsonlSupportEvidence:
        return jsonl.inspect_jsonl_bronze_support(
            proof_bronze,
            support=support,
            plan_bytes=proof_plan,
            expected_plan_sha256=expected_proof_plan_sha256,
        )

    def complete(value: jsonl.JsonlSupportEvidence) -> bool:
        return (
            type(value) is jsonl.JsonlSupportEvidence
            and value.version == jsonl.VERSION
            and value.status == "verified_jsonl_recomputation"
            and value.artifact_to_event_semantics_verified is True
            and value.original_plan_binding_verified is True
            and pin(value.evidence_fingerprint)
            and all(
                flag is False
                for flag in (
                    value.identity_semantics_verified,
                    value.source_acquisition_authenticity_asserted,
                    value.issuer_authenticated,
                    value.identity_verified,
                    value.retry_link_coverage_verified,
                    value.availability_evidence_verified,
                    value.historical_validity_asserted,
                    value.decision_eligibility_asserted,
                    value.atomic_cross_database_snapshot_asserted,
                )
            )
        )

    before = observe()
    if not complete(before):
        return SignatureReceiptEvidence(
            VERSION,
            assertion_id,
            "review_required",
            ("SIGNATURE_PROOF_STORAGE_NOT_COMPLETE",),
            before,
        )
    proof_bronze.execute("BEGIN TRANSACTION")
    try:
        table = source._name(proof_bronze, "bronze", "event_variants")
        variants = source._select(
            proof_bronze,
            table,
            ("envelope_hash",),
            "capture_event_id=?",
            [support.capture_event_id],
            2,
        )
        rows = source._select(
            proof_bronze,
            table,
            source.EVENT_COLUMNS,
            "capture_event_id=? AND envelope_hash=?",
            [support.capture_event_id, support.envelope_hash],
            1,
        )
        if variants != [(support.envelope_hash,)] or len(rows) != 1:
            raise SignatureArtifactRejected("SIGNATURE_PROOF_RECEIPT_CONFLICT_OR_MISSING")
        source._verify_event(rows[0])
        raw = rows[0][9]
        if (
            rows[0][11] != PAYLOAD_FORMAT
            or len(raw) != support.byte_end
            or sha(raw) != support.payload_hash
        ):
            raise SignatureArtifactRejected("SIGNATURE_PROOF_FORMAT_OR_WHOLE_PAYLOAD_MISMATCH")
        artifact = parse_signature_artifact(raw)
    except BaseException:
        proof_bronze.execute("ROLLBACK")
        raise
    proof_bronze.execute("COMMIT")
    if (artifact.assertion_id, artifact.record_id, artifact.payload_sha256) != (
        assertion_id,
        record_id,
        checked.evidence_payload_hash,
    ):
        return SignatureReceiptEvidence(
            VERSION,
            assertion_id,
            "review_required",
            ("SIGNATURE_PROOF_TARGET_MISMATCH",),
            before,
            artifact=artifact,
        )

    def bind() -> binding.RecordedStatementSignature:
        return binding.inspect_recorded_statement_signature(
            registry,
            bronze,
            assertion_id=assertion_id,
            request=checked,
            record_id=record_id,
            original_plan=original_plan,
            expected_plan_sha256=expected_plan_sha256,
            payload=payload,
            signature=artifact.signature,
            public_key=artifact.public_key,
            expected_public_key_sha256=expected_public_key_sha256,
        )

    first = bind()
    after = observe()
    second = bind()
    reasons: list[str] = []
    if not complete(after) or canonical(asdict(before)) != canonical(asdict(after)):
        reasons.append("SIGNATURE_PROOF_STORAGE_OR_DERIVATION_CHANGED")
    if (
        not first.recorded_payload_signature_bound
        or not second.recorded_payload_signature_bound
        or not pin(first.evidence_fingerprint)
        or not pin(second.evidence_fingerprint)
        or canonical(asdict(first)) != canonical(asdict(second))
    ):
        reasons.append("RECORDED_SIGNATURE_BINDING_NOT_COMPLETE_OR_CHANGED")
    if reasons:
        return SignatureReceiptEvidence(
            VERSION,
            assertion_id,
            "review_required",
            tuple(reasons),
            before,
            after,
            first,
            second,
            artifact,
        )
    # Artifact byte fields use a digest-only canonical projection, never JSON raw bytes.
    artifact_pin = [
        artifact.version,
        artifact.artifact_sha256,
        artifact.assertion_id,
        artifact.record_id,
        artifact.payload_sha256,
    ]
    fingerprint = sha(
        canonical(
            [
                VERSION,
                asdict(support),
                expected_proof_plan_sha256,
                artifact_pin,
                asdict(before),
                asdict(after),
                asdict(first),
                asdict(second),
            ]
        ).encode()
    )
    return SignatureReceiptEvidence(
        VERSION,
        assertion_id,
        "recorded_signature_proof_storage_linked",
        ("EXACT_SIGNATURE_ARTIFACT_RECEIPT_AND_BINDING_LINKED",),
        before,
        after,
        first,
        second,
        artifact,
        True,
        fingerprint,
    )
