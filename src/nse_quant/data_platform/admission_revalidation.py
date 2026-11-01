"""Fresh request revalidation of a pinned capture, not authority or decision execution."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any

from nse_quant.data_platform import admission_capture as store
from nse_quant.data_platform import admission_capture_reader as archive
from nse_quant.data_platform import publication_admission as policy
from nse_quant.data_platform.feature_bundle import valid_pin

VERSION = "captured-publication-request-revalidation@1"
ARCHIVE_VERSION = "publication-admission-capture-consumer@1"


@dataclass(frozen=True)
class AdmissionRevalidation:
    version: str
    receipt_id: str
    publication_id: str
    status: str
    reason_codes: tuple[str, ...]
    archived_capture_verified: bool = False
    current_request_checked: bool = False
    observed_inputs_match: bool = False
    research_policy_satisfied: bool = False
    fresh_receipt_id: str | None = None
    fresh_policy_status: str | None = None
    evidence_fingerprint: str | None = None
    research_analysis_authorized: bool = False
    decision_eligibility_asserted: bool = False
    availability_evidence_verified: bool = False
    economic_validity_verified: bool = False
    source_current_checked: bool = False
    replay_authenticity_asserted: bool = False
    atomic_cross_database_snapshot_asserted: bool = False


def _request(request: policy.AdmissionRequest) -> dict[str, object]:
    checked = policy.AdmissionRequest(
        request.use_case, request.knowledge_cutoff, request.economic_at
    )
    return {
        "use_case": checked.use_case,
        "knowledge_cutoff": store._clock(checked.knowledge_cutoff),
        "economic_at": store._clock(checked.economic_at),
    }


def _trusted_head(value: archive.AdmissionCaptureEvidence, pin: str) -> bool:
    return (
        type(value) is archive.AdmissionCaptureEvidence
        and value.reader_version == ARCHIVE_VERSION
        and value.receipt_id == pin
        and value.status == "verified_archived_capture"
        and value.archived_integrity_verified is True
        and value.native_capture_provenance_verified is True
        and value.reassessment_history_verified is True
        and value.pinned_receipt_is_history_head is True
        and value.history_head_receipt_id == pin
        and value.current_request_checked is False
        and value.research_analysis_authorized is False
        and value.decision_eligibility_asserted is False
        and value.replay_authenticity_asserted is False
    )


def revalidate_captured_publication_use(
    publications: Any,
    captures: Any,
    *,
    receipt_id: str,
    publication_id: str,
    request: policy.AdmissionRequest,
) -> AdmissionRevalidation:
    """Separate owned file-backed read-only connections; no outer transactions.

    Two archive observations bracket two fresh native policy assessments. Compare
    exact encoded receipt bytes, not policy status alone. No writes or automatic
    new capture. Observed agreement is not an atomic snapshot, ACL or market-time
    assertion. SQL/source failures propagate, never become business rejection.
    """
    if not valid_pin(receipt_id) or not valid_pin(publication_id):
        raise ValueError("EXACT_REVALIDATION_PINS_REQUIRED")
    if not isinstance(request, policy.AdmissionRequest):
        raise TypeError("TYPED_REVALIDATION_REQUEST_REQUIRED")
    if (
        policy.POLICY_VERSION != "research-publication-admission@1"
        or store.STORE_VERSION != "publication-admission-capture@1"
        or archive.READER_VERSION != ARCHIVE_VERSION
    ):
        raise ValueError("UNSUPPORTED_REVALIDATION_DEPENDENCY_VERSION")
    requested = _request(request)
    if not store._file_backed(publications) or not store._file_backed(captures):
        raise ValueError("FILE_BACKED_REVALIDATION_INPUTS_REQUIRED")
    if publications is captures or any(
        a == b or (a.exists() and b.exists() and a.samefile(b))
        for a in store._paths(publications)
        for b in store._paths(captures)
    ):
        raise ValueError("SEPARATE_REVALIDATION_DATABASES_REQUIRED")

    def report(status: str, reasons: tuple[str, ...], **values: Any) -> AdmissionRevalidation:
        return AdmissionRevalidation(VERSION, receipt_id, publication_id, status, reasons, **values)

    before = archive.read_admission_capture(captures, receipt_id=receipt_id)
    if not _trusted_head(before, receipt_id):
        return report("review_required", ("CAPTURE_NOT_VERIFIED_HISTORY_HEAD",))
    captured, _, _, _ = archive._record(captures, receipt_id)
    frozen = json.loads(captured.frozen_input_json)
    if captured.publication_id != publication_id or policy._canonical(frozen["request"]) != (
        policy._canonical(requested)
    ):
        return report(
            "review_required",
            ("CAPTURE_PUBLICATION_OR_REQUEST_PIN_MISMATCH",),
            archived_capture_verified=True,
        )
    if before.archived_policy_status != captured.status:
        return report("review_required", ("CAPTURE_OBSERVATION_DRIFT",))
    original_bytes = policy.encode_admission_receipt(captured)
    fresh = policy.assess_publication_use(
        publications, publication_id=publication_id, request=request
    )
    fresh_bytes = policy.encode_admission_receipt(fresh)
    repeated = policy.assess_publication_use(
        publications, publication_id=publication_id, request=request
    )
    repeated_bytes = policy.encode_admission_receipt(repeated)
    after = archive.read_admission_capture(captures, receipt_id=receipt_id)
    if not _trusted_head(after, receipt_id) or asdict(before) != asdict(after):
        return report(
            "review_required", ("CAPTURE_OBSERVATION_DRIFT",), current_request_checked=True
        )
    final_capture, _, _, _ = archive._record(captures, receipt_id)
    if policy.encode_admission_receipt(final_capture) != original_bytes:
        return report(
            "review_required", ("CAPTURE_OBSERVATION_DRIFT",), current_request_checked=True
        )
    if fresh_bytes != repeated_bytes:
        return report(
            "review_required",
            ("PUBLICATION_ASSESSMENT_OBSERVATION_DRIFT",),
            archived_capture_verified=True,
            current_request_checked=True,
        )
    fresh_input = json.loads(fresh.frozen_input_json)
    if fresh.publication_id != publication_id or policy._canonical(fresh_input["request"]) != (
        policy._canonical(requested)
    ):
        raise ValueError("FRESH_REVALIDATION_CONTRACT_MISMATCH")
    fingerprint = hashlib.sha256(
        policy._canonical(
            [
                VERSION,
                asdict(before),
                asdict(after),
                receipt_id,
                fresh.receipt_id,
                hashlib.sha256(original_bytes).hexdigest(),
                hashlib.sha256(fresh_bytes).hexdigest(),
            ]
        ).encode()
    ).hexdigest()
    facts: dict[str, Any] = {
        "archived_capture_verified": True,
        "current_request_checked": True,
        "observed_inputs_match": fresh_bytes == original_bytes,
        "fresh_receipt_id": fresh.receipt_id,
        "fresh_policy_status": fresh.status,
        "evidence_fingerprint": fingerprint,
    }
    if fresh_bytes != original_bytes:
        return report(
            "review_required", ("FRESH_INPUT_DIFFERS_FROM_CAPTURE_REASSESS_EXPLICITLY",), **facts
        )
    if fresh.status == "REJECTED":
        return report("rejected", fresh.reason_codes, **facts)
    if (
        request.use_case != policy.ARCHIVED_RESEARCH
        or fresh.status != "ACCEPTED_RESEARCH_ONLY"
        or fresh.research_analysis_permitted is not True
        or any(
            flag is not False
            for flag in (
                fresh.decision_eligibility_asserted,
                fresh.availability_evidence_verified,
                fresh.economic_validity_verified,
                fresh.source_current_checked,
                fresh.replay_authenticity_asserted,
            )
        )
    ):
        raise ValueError("UNSUPPORTED_REVALIDATION_POLICY_RESULT")
    return report(
        "matched_research_input",
        ("EXACT_CAPTURE_AND_FRESH_RESEARCH_INPUT_MATCH",),
        research_policy_satisfied=True,
        **facts,
    )
