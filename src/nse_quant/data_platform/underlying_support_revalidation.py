"""Exact recorded assertion + current support observations; never identity authority."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from nse_quant.data_platform.bronze_support_reader import (
        BronzeSupportEvidence,
        IngestAuditExpectation,
    )
    from nse_quant.data_platform.underlying_assertion import UnderlyingAssertionRequest
    from nse_quant.data_platform.underlying_assertion_reader import UnderlyingAssertionRecording

VERSION = "underlying-assertion-support-revalidation@1"
MAX_STATEMENT_BYTES = 16384


def _pin(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _same(left: object, right: object) -> bool:
    """Canonical comparison, not Python bool/int-coercing equality."""
    return _canonical(left) == _canonical(right)


def _distinct_files(registry: Any, bronze: Any) -> None:
    paths: list[set[Path]] = []
    for connection in (registry, bronze):
        current = connection.execute("SELECT current_database()").fetchone()
        databases = connection.execute("PRAGMA database_list").fetchall()
        if current is None or not any(row[1] == current[0] and row[2] for row in databases):
            raise ValueError("FILE_BACKED_UNDERLYING_REVALIDATION_INPUTS_REQUIRED")
        paths.append({Path(row[2]).resolve() for row in databases if row[2]})
    if registry is bronze or any(
        a == b or (a.exists() and b.exists() and a.samefile(b)) for a in paths[0] for b in paths[1]
    ):
        raise ValueError("SEPARATE_UNDERLYING_REVALIDATION_DATABASES_REQUIRED")


def _statement_bytes(registry: Any, assertion_id: str) -> bytes | None:
    """Bounded exact retrieval only, NOT native recording/provenance verification."""
    if not _pin(assertion_id):
        raise ValueError("EXACT_UNDERLYING_REVALIDATION_PIN_REQUIRED")
    current = registry.execute("SELECT current_database()").fetchone()
    if current is None:
        raise ValueError("UNDERLYING_REVALIDATION_CATALOG_UNAVAILABLE")
    table = ".".join(
        '"' + str(x).replace('"', '""') + '"'
        for x in (current[0], "identity_evidence", "assertions")
    )
    rows = registry.execute(
        f"SELECT CASE WHEN octet_length(assertion_bytes)<=? THEN assertion_bytes END "
        f"FROM {table} WHERE assertion_id=? LIMIT 2",
        [MAX_STATEMENT_BYTES, assertion_id],
    ).fetchall()
    if len(rows) != 1 or not isinstance(rows[0][0], bytes):
        return None
    return rows[0][0]


@dataclass(frozen=True)
class UnderlyingSupportRevalidation:
    version: str
    assertion_id: str
    status: str
    reason_codes: tuple[str, ...]
    recording_before: UnderlyingAssertionRecording | None = None
    recording_after: UnderlyingAssertionRecording | None = None
    support_before: BronzeSupportEvidence | None = None
    support_after: BronzeSupportEvidence | None = None
    current_support_checked: bool = False
    exact_recorded_request_matched: bool = False
    registry_unchanged_observed: bool = False
    bronze_support_unchanged_observed: bool = False
    evidence_fingerprint: str | None = None
    identity_verified: bool = False
    issuer_authenticated: bool = False
    canonical_underlying_id: None = None
    artifact_to_event_semantics_verified: bool = False
    retry_link_coverage_verified: bool = False
    bronze_acquisition_provenance_verified: bool = False
    availability_evidence_verified: bool = False
    historical_validity_asserted: bool = False
    decision_eligibility_asserted: bool = False
    atomic_cross_database_snapshot_asserted: bool = False


def revalidate_underlying_assertion_support(
    registry: Any,
    bronze: Any,
    *,
    assertion_id: str,
    request: UnderlyingAssertionRequest,
    expected_audit: IngestAuditExpectation,
) -> UnderlyingSupportRevalidation:
    """Owned read-only separate file-backed inputs; no enclosing transactions.

    No as-of claims or writes. Exact request must hash to the explicit statement
    pin. Full recording history resolves before support checks or statement-kind
    interpretation. Last distinct statement is an evidence position, not authority.
    Two fresh source observations bracketed by full registry fingerprints establish
    observed agreement only. SQL/operational failures propagate without rejection.
    """
    from nse_quant.data_platform import bronze_support_reader as source
    from nse_quant.data_platform import underlying_assertion as kernel
    from nse_quant.data_platform import underlying_assertion_reader as archive
    from nse_quant.data_platform.underlying_support_adapter import (
        inspect_underlying_support_storage,
    )

    if not _pin(assertion_id):
        raise ValueError("EXACT_UNDERLYING_REVALIDATION_PIN_REQUIRED")
    if not isinstance(request, kernel.UnderlyingAssertionRequest) or not isinstance(
        expected_audit, source.IngestAuditExpectation
    ):
        raise TypeError("TYPED_UNDERLYING_REVALIDATION_INPUTS_REQUIRED")
    checked = kernel.UnderlyingAssertionRequest(**asdict(request))
    audit = source.IngestAuditExpectation(**asdict(expected_audit))
    if (
        archive.VERSION != "underlying-assertion-recording-consumer@1"
        or source.VERSION != "pinned-bronze-support-storage@1"
        or kernel.VERSION != "underlying-identity-assertion@1"
    ):
        raise ValueError("UNSUPPORTED_UNDERLYING_REVALIDATION_DEPENDENCY_VERSION")
    expected = kernel.make_underlying_assertion(checked)
    expected_bytes = kernel.encode_underlying_assertion(expected)

    def report(reasons: tuple[str, ...], **facts: Any) -> UnderlyingSupportRevalidation:
        return UnderlyingSupportRevalidation(
            VERSION, assertion_id, "review_required", reasons, **facts
        )

    if expected.assertion_id != assertion_id:
        return report(("EXPLICIT_REQUEST_DOES_NOT_MATCH_ASSERTION_PIN",))
    _distinct_files(registry, bronze)

    def complete_recording(value: archive.UnderlyingAssertionRecording) -> bool:
        return (
            type(value) is archive.UnderlyingAssertionRecording
            and value.version == archive.VERSION
            and value.assertion_id == assertion_id
            and value.status == "verified_archived_recording"
            and value.archived_integrity_verified is True
            and value.native_recording_provenance_verified is True
            and value.registry_history_verified is True
            and value.pinned_is_last_distinct_statement is True
            and value.last_distinct_statement_id == assertion_id
            and value.archived_assertion_kind == checked.assertion
            and value.audit_obligation_job_ids == ()
            and _pin(value.evidence_fingerprint)
            and value.canonical_underlying_id is None
            and all(
                flag is False
                for flag in (
                    value.current_bronze_support_checked,
                    value.bronze_acquisition_provenance_verified,
                    value.identity_verified,
                    value.issuer_authenticated,
                    value.historical_validity_asserted,
                    value.availability_evidence_verified,
                    value.decision_eligibility_asserted,
                )
            )
        )

    def complete_support(value: source.BronzeSupportEvidence) -> bool:
        return (
            type(value) is source.BronzeSupportEvidence
            and value.version == source.VERSION
            and value.capture_event_id == checked.bronze_capture_event_id
            and value.status == "verified_storage_evidence"
            and value.current_payload_integrity_verified is True
            and value.retained_input_artifact_verified is True
            and value.fresh_batch_membership_verified is True
            and value.origin_ingest_audit_verified is True
            and value.scoped_audit_history_verified is True
            and value.audit_obligation_job_ids == ()
            and _pin(value.evidence_fingerprint)
            and all(
                flag is False
                for flag in (
                    value.retry_link_coverage_verified,
                    value.artifact_to_event_semantics_verified,
                    value.source_acquisition_authenticity_asserted,
                    value.identity_verified,
                    value.issuer_authenticated,
                    value.availability_evidence_verified,
                    value.historical_validity_asserted,
                    value.decision_eligibility_asserted,
                )
            )
        )

    before = archive.read_underlying_assertion_recording(registry, assertion_id=assertion_id)
    if not complete_recording(before):
        return report(("PINNED_RECORDING_NOT_LAST_COMPLETE_EVIDENCE",), recording_before=before)
    raw_before = _statement_bytes(registry, assertion_id)
    if raw_before is None or raw_before != expected_bytes:
        return report(("RECORDED_REQUEST_BYTES_DO_NOT_MATCH",), recording_before=before)
    # Decode through the native codec too: a self-consistent outer request is not provenance.
    kernel.decode_underlying_assertion(raw_before, expected_assertion_id=assertion_id)
    first = inspect_underlying_support_storage(bronze, request=checked, expected_audit=audit)
    second = inspect_underlying_support_storage(bronze, request=checked, expected_audit=audit)
    after = archive.read_underlying_assertion_recording(registry, assertion_id=assertion_id)
    raw_after = _statement_bytes(registry, assertion_id)
    registry_same = (
        complete_recording(after)
        and _same(asdict(before), asdict(after))
        and raw_after == raw_before
    )
    support_same = _same(asdict(first), asdict(second))
    support_complete = complete_support(first) and complete_support(second)
    reasons: tuple[str, ...] = tuple(
        reason
        for condition, reason in (
            (not registry_same, "REGISTRY_RECORDING_OBSERVATION_CHANGED_OR_BLOCKED"),
            (not support_same, "BRONZE_SUPPORT_OBSERVATION_CHANGED"),
            (not support_complete, "CURRENT_BRONZE_STORAGE_NOT_VERIFIED"),
        )
        if condition
    )
    facts: dict[str, Any] = dict(
        recording_before=before,
        recording_after=after,
        support_before=first,
        support_after=second,
        current_support_checked=True,
        exact_recorded_request_matched=raw_after == expected_bytes,
        registry_unchanged_observed=registry_same,
        bronze_support_unchanged_observed=support_same,
    )
    if reasons:
        return report(reasons, **facts)
    fingerprint = hashlib.sha256(
        _canonical(
            [
                VERSION,
                assertion_id,
                hashlib.sha256(expected_bytes).hexdigest(),
                asdict(audit),
                asdict(before),
                asdict(after),
                asdict(first),
                asdict(second),
            ]
        ).encode()
    ).hexdigest()
    return UnderlyingSupportRevalidation(
        VERSION,
        assertion_id,
        "verified_recording_and_current_storage",
        ("UNVERIFIED_STATEMENT_RECORDING_AND_CURRENT_STORAGE_OBSERVED_CONSISTENT",),
        evidence_fingerprint=fingerprint,
        **facts,
    )
