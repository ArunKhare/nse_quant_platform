"""Recorded assertion -> JSONL derivation -> exact untrusted statement content."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from nse_quant.data_platform.identity_statement_document import (
    PAYLOAD_FORMAT,
    StatementContentMatch,
    StatementDocumentRejected,
    StatementExpectation,
    canonical,
    match_statement_content,
    pin,
    sha,
)

if TYPE_CHECKING:
    from nse_quant.data_platform.bronze_jsonl_support_reader import JsonlSupportEvidence
    from nse_quant.data_platform.underlying_assertion import UnderlyingAssertionRequest
    from nse_quant.data_platform.underlying_support_revalidation import (
        UnderlyingSupportRevalidation,
    )

VERSION = "recorded-identity-statement-content@1"


@dataclass(frozen=True)
class RecordedStatementContent:
    version: str
    assertion_id: str
    status: str
    reason_codes: tuple[str, ...]
    recording_before: UnderlyingSupportRevalidation | None = None
    recording_after: UnderlyingSupportRevalidation | None = None
    jsonl_before: JsonlSupportEvidence | None = None
    jsonl_after: JsonlSupportEvidence | None = None
    content: StatementContentMatch | None = None
    statement_content_matched: bool = False
    exact_record_span_verified: bool = False
    jsonl_derivation_verified: bool = False
    evidence_fingerprint: str | None = None
    identity_verified: bool = False
    issuer_authenticated: bool = False
    canonical_underlying_id: None = None
    authorized_revocation_asserted: bool = False
    availability_evidence_verified: bool = False
    historical_validity_asserted: bool = False
    decision_eligibility_asserted: bool = False
    atomic_cross_database_snapshot_asserted: bool = False


def inspect_recorded_statement_content(
    registry: Any,
    bronze: Any,
    *,
    assertion_id: str,
    request: UnderlyingAssertionRequest,
    record_id: str,
    original_plan: bytes,
    expected_plan_sha256: str,
) -> RecordedStatementContent:
    """Read-only owned inputs, no outer transactions. Matching is NOT issuer trust.

    Platform-owned statement schema only, never auto-detected from arbitrary payloads.
    Current native full-history gates run before source content selection. No writes,
    repair, provider acquisition, canonical mapping or authenticated withdrawal path.
    """
    from nse_quant.data_platform import bronze_jsonl_recompute as codec
    from nse_quant.data_platform import bronze_jsonl_support_reader as jsonl
    from nse_quant.data_platform import bronze_support_reader as source
    from nse_quant.data_platform import underlying_assertion as kernel
    from nse_quant.data_platform import underlying_support_revalidation as recording

    if (
        recording.VERSION != "underlying-assertion-support-revalidation@1"
        or jsonl.VERSION != "bronze-jsonl-support-consumer@1"
        or codec.VERSION != "bronze-jsonl-envelope-recompute@1"
    ):
        raise ValueError("UNSUPPORTED_STATEMENT_CONTENT_DEPENDENCY_VERSION")
    if not isinstance(request, kernel.UnderlyingAssertionRequest) or not pin(assertion_id):
        raise ValueError("EXACT_TYPED_STATEMENT_CONTENT_INPUTS_REQUIRED")
    checked = kernel.UnderlyingAssertionRequest(**asdict(request))
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
    plan = codec.decode_import_plan(original_plan, expected_plan_sha256=expected_plan_sha256)
    audit = source.IngestAuditExpectation(
        codec.COMMAND, "sha256:" + plan.plan_sha256, codec.CONFIG_HASH
    )
    support = source.BronzeSupportPin(
        checked.bronze_capture_event_id,
        checked.bronze_envelope_hash,
        checked.evidence_payload_hash,
        checked.evidence_byte_start,
        checked.evidence_byte_end,
        checked.evidence_fragment_sha256,
    )

    def full_recording(value: recording.UnderlyingSupportRevalidation) -> bool:
        return (
            type(value) is recording.UnderlyingSupportRevalidation
            and value.version == recording.VERSION
            and value.assertion_id == assertion_id
            and value.status == "verified_recording_and_current_storage"
            and value.current_support_checked is True
            and value.exact_recorded_request_matched is True
            and value.registry_unchanged_observed is True
            and value.bronze_support_unchanged_observed is True
            and pin(value.evidence_fingerprint)
            and value.canonical_underlying_id is None
            and all(
                flag is False
                for flag in (
                    value.identity_verified,
                    value.issuer_authenticated,
                    value.artifact_to_event_semantics_verified,
                    value.retry_link_coverage_verified,
                    value.bronze_acquisition_provenance_verified,
                    value.availability_evidence_verified,
                    value.historical_validity_asserted,
                    value.decision_eligibility_asserted,
                    value.atomic_cross_database_snapshot_asserted,
                )
            )
        )

    def full_jsonl(value: jsonl.JsonlSupportEvidence) -> bool:
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

    before = recording.revalidate_underlying_assertion_support(
        registry,
        bronze,
        assertion_id=assertion_id,
        request=checked,
        expected_audit=audit,
    )
    if not full_recording(before):
        return RecordedStatementContent(
            VERSION,
            assertion_id,
            "review_required",
            ("RECORDED_STATEMENT_NOT_CURRENT_COMPLETE_EVIDENCE",),
            before,
        )
    derivation_before = jsonl.inspect_jsonl_bronze_support(
        bronze,
        support=support,
        plan_bytes=original_plan,
        expected_plan_sha256=expected_plan_sha256,
    )
    if not full_jsonl(derivation_before):
        return RecordedStatementContent(
            VERSION,
            assertion_id,
            "review_required",
            ("STATEMENT_JSONL_DERIVATION_NOT_VERIFIED",),
            recording_before=before,
            jsonl_before=derivation_before,
        )
    content = None
    content_reasons: tuple[str, ...] = ()
    bronze.execute("BEGIN TRANSACTION")
    try:
        table = source._name(bronze, "bronze", "event_variants")
        variants = source._select(
            bronze, table, ("envelope_hash",), "capture_event_id=?", [support.capture_event_id], 2
        )
        rows = source._select(
            bronze,
            table,
            source.EVENT_COLUMNS,
            "capture_event_id=? AND envelope_hash=?",
            [support.capture_event_id, support.envelope_hash],
            1,
        )
        if variants != [(support.envelope_hash,)] or len(rows) != 1:
            raise StatementDocumentRejected("STATEMENT_SOURCE_CONFLICT_OR_MISSING")
        source._verify_event(rows[0])
        if rows[0][11] != PAYLOAD_FORMAT:
            raise StatementDocumentRejected("STATEMENT_PAYLOAD_FORMAT_NOT_SUPPORTED")
        content = match_statement_content(rows[0][9], expected=expected)
    except (StatementDocumentRejected, source.SupportReviewRequired) as error:
        content_reasons = (str(error),)
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError):
        content_reasons = ("STATEMENT_DOCUMENT_CONTENT_NOT_VERIFIED",)
    except BaseException:
        bronze.execute("ROLLBACK")
        raise
    bronze.execute("COMMIT")
    derivation_after = jsonl.inspect_jsonl_bronze_support(
        bronze,
        support=support,
        plan_bytes=original_plan,
        expected_plan_sha256=expected_plan_sha256,
    )
    after = recording.revalidate_underlying_assertion_support(
        registry,
        bronze,
        assertion_id=assertion_id,
        request=checked,
        expected_audit=audit,
    )
    consistent = (
        full_recording(after)
        and full_jsonl(derivation_after)
        and canonical(asdict(before)) == canonical(asdict(after))
        and canonical(asdict(derivation_before)) == canonical(asdict(derivation_after))
    )
    storage_views = (
        before.support_before,
        before.support_after,
        after.support_before,
        after.support_after,
        derivation_before.storage_before,
        derivation_before.storage_after,
        derivation_after.storage_before,
        derivation_after.storage_after,
    )
    storage_hashes = [view.evidence_fingerprint for view in storage_views if view is not None]
    consistent = consistent and len(storage_hashes) == 8 and len(set(storage_hashes)) == 1
    matched = (
        content is not None
        and content.status == "matched_unverified_statement_content"
        and content.statement_content_matched is True
        and content.record_span_verified is True
    )
    reasons: tuple[str, ...] = content_reasons or (
        content.reason_codes if content is not None and not matched else ()
    )
    if not consistent:
        reasons += ("STATEMENT_RECORDING_OR_DERIVATION_OBSERVATION_DRIFT",)
    if not matched and not reasons:
        reasons = ("STATEMENT_CONTENT_NOT_MATCHED",)
    if reasons or content is None:
        return RecordedStatementContent(
            VERSION,
            assertion_id,
            "review_required",
            reasons,
            before,
            after,
            derivation_before,
            derivation_after,
            content,
        )
    fingerprint = sha(
        canonical(
            [
                VERSION,
                assertion_id,
                record_id,
                plan.plan_sha256,
                asdict(before),
                asdict(after),
                asdict(derivation_before),
                asdict(derivation_after),
                asdict(content),
            ]
        ).encode()
    )
    return RecordedStatementContent(
        VERSION,
        assertion_id,
        "matched_untrusted_statement_support",
        ("EXACT_RECORDED_UNTRUSTED_STATEMENT_CONTENT_MATCHED",),
        before,
        after,
        derivation_before,
        derivation_after,
        content,
        True,
        True,
        True,
        fingerprint,
    )
