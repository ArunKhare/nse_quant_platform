"""Purpose-aware research admission of pinned window publications; never trade permission."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from nse_quant.data_platform import legacy_window_publication as publication
from nse_quant.data_platform.publication_admission import (
    ARCHIVED_RESEARCH,
    AdmissionRequest,
    _request_dict,
    _request_from_json,
)

VERSION = "legacy-window-research-admission@1"
MAX_BYTES = 32768
DEFINITION = (
    VERSION,
    publication.VERSION,
    publication.POLICY_VERSION,
    "actual pinned complete archived publication, never current upstream or authority",
    "all rows retained including unavailable windows; archival analysis is not a strategy permit",
    "POINT_IN_TIME_DECISION always refused; record/audit clocks are not availability",
    "summary-only policy replay does not authenticate original source evidence",
)


@dataclass(frozen=True)
class WindowResearchAdmission:
    receipt_id: str
    frozen_input_json: str
    policy_status: str
    reason_codes: tuple[str, ...]
    research_analysis_permitted: bool
    policy_version: str = VERSION
    decision_eligibility_asserted: bool = False
    research_analysis_authorized: bool = False
    availability_verified: bool = False
    economic_validity_verified: bool = False
    authoritative_market_coverage_verified: bool = False
    canonical_contract_id: None = None
    current_native_upstream_checked: bool = False
    replay_authenticity_asserted: bool = False


def _summary(value: publication.WindowPublication) -> dict[str, object]:
    return dict(
        publication_id=value.publication_id,
        recording_fingerprint=value.recording_fingerprint,
        bundle_id=value.bundle_id,
        window_build_id=value.request.build_id,
        policy=json.loads(value.policy_json),
        row_count=value.row_count,
        purpose=value.purpose,
        publication_recorded_at=value.publication_recorded_at,
        origin_audit_success_recorded_at=value.origin_audit_success_recorded_at,
        clock_semantics=value.clock_semantics,
        research_publication_verified=value.research_publication_verified,
        current_source_checked=value.current_source_checked,
        decision_eligibility_asserted=value.decision_eligibility_asserted,
        availability_verified=value.availability_verified,
        economic_validity_verified=value.economic_validity_verified,
        authoritative_market_coverage_verified=value.authoritative_market_coverage_verified,
        canonical_contract_id=value.canonical_contract_id,
    )


def _evaluate(frozen: str) -> WindowResearchAdmission:
    if type(frozen) is not str or not 0 < len(frozen.encode()) <= MAX_BYTES:
        raise ValueError("WINDOW_ADMISSION_INPUT_BYTE_BOUND")
    try:
        doc = json.loads(frozen)
        if (
            type(doc) is not dict
            or set(doc) != {"definition", "request", "source"}
            or doc["definition"] != publication.native._hash(DEFINITION)
            or publication.native._canonical(doc) != frozen
        ):
            raise ValueError("WINDOW_ADMISSION_INPUT_CONTRACT")
        request = _request_from_json(doc["request"])
        source = doc["source"]
        fields = {
            "publication_id",
            "recording_fingerprint",
            "bundle_id",
            "window_build_id",
            "policy",
            "row_count",
            "purpose",
            "publication_recorded_at",
            "origin_audit_success_recorded_at",
            "clock_semantics",
            "research_publication_verified",
            "current_source_checked",
            "decision_eligibility_asserted",
            "availability_verified",
            "economic_validity_verified",
            "authoritative_market_coverage_verified",
            "canonical_contract_id",
        }
        if (
            type(source) is not dict
            or set(source) != fields
            or any(
                not publication.bundle.pin(source[k])
                for k in ("publication_id", "recording_fingerprint", "bundle_id", "window_build_id")
            )
            or source["publication_id"]
            != publication.publication_id(source["window_build_id"], source["bundle_id"])
            or source["purpose"] != publication.PURPOSE
            or source["clock_semantics"] != publication.CLOCK
            or source["research_publication_verified"] is not True
            or source["canonical_contract_id"] is not None
            or type(source["row_count"]) is not int
            or not 1 <= source["row_count"] <= 16000
            or any(
                source[k] is not False
                for k in (
                    "current_source_checked",
                    "decision_eligibility_asserted",
                    "availability_verified",
                    "economic_validity_verified",
                    "authoritative_market_coverage_verified",
                )
            )
        ):
            raise ValueError("WINDOW_ADMISSION_SOURCE_SUMMARY_CONTRACT")
        policy = publication.bundle.source.features.ReturnWindowPolicy(**source["policy"])
        if asdict(policy) != source["policy"]:
            raise ValueError("WINDOW_ADMISSION_POLICY_CONTRACT")
        for key in ("publication_recorded_at", "origin_audit_success_recorded_at"):
            raw = source[key]
            if (
                type(raw) is not str
                or publication.native._instant(datetime.fromisoformat(raw)) != raw
            ):
                raise ValueError("WINDOW_ADMISSION_RECORD_CLOCK_CONTRACT")
    except (TypeError, KeyError, RecursionError, OverflowError):
        raise ValueError("WINDOW_ADMISSION_MALFORMED_INPUT") from None
    permitted = request.use_case == ARCHIVED_RESEARCH
    reasons = (
        ("VERIFIED_ARCHIVED_WINDOW_RESEARCH_PUBLICATION", "NO_POINT_IN_TIME_CLAIM")
        if permitted
        else (
            "RESEARCH_ONLY_PURPOSE_NOT_DECISION_INPUT",
            "AVAILABILITY_EVIDENCE_UNKNOWN",
            "ECONOMIC_VALIDITY_EVIDENCE_UNKNOWN",
            "CANONICAL_IDENTITY_UNKNOWN",
            "MARKET_COVERAGE_NOT_AUTHENTICATED",
            "RECORD_CLOCKS_NOT_AVAILABILITY_PROOF",
            "DECISION_ELIGIBILITY_NOT_ASSERTED",
        )
    )
    result = WindowResearchAdmission(
        "", frozen, "ACCEPTED_RESEARCH_ONLY" if permitted else "REJECTED", reasons, permitted
    )
    identity = publication.native._hash(
        {k: v for k, v in asdict(result).items() if k != "receipt_id"}
    )
    return WindowResearchAdmission(**dict(asdict(result), receipt_id=identity))


def assess_window_publication_use(
    publications: Any,
    *,
    publication_id: str,
    expected_recording_fingerprint: str,
    request: AdmissionRequest,
) -> WindowResearchAdmission:
    if type(request) is not AdmissionRequest:
        raise TypeError("TYPED_WINDOW_ADMISSION_REQUEST_REQUIRED")
    request = AdmissionRequest(request.use_case, request.knowledge_cutoff, request.economic_at)
    args = dict(
        publication_id=publication_id, expected_recording_fingerprint=expected_recording_fingerprint
    )
    first = publication.read_window_publication(publications, **args)
    frozen = publication.native._canonical(
        dict(
            definition=publication.native._hash(DEFINITION),
            request=_request_dict(request),
            source=_summary(first),
        )
    )
    if publication.read_window_publication(publications, **args) != first:
        raise ValueError("WINDOW_ADMISSION_PUBLICATION_OBSERVATION_DRIFT")
    return _evaluate(frozen)


def encode_window_admission(receipt: WindowResearchAdmission) -> bytes:
    if type(receipt) is not WindowResearchAdmission or receipt != _evaluate(
        receipt.frozen_input_json
    ):
        raise ValueError("WINDOW_ADMISSION_RESULT_MISMATCH")
    raw = publication.native._canonical(
        {k: v for k, v in asdict(receipt).items() if k != "receipt_id"}
    ).encode()
    if len(raw) > MAX_BYTES:
        raise ValueError("WINDOW_ADMISSION_RECEIPT_BYTE_BOUND")
    return raw


def replay_window_admission(raw: bytes, *, expected_receipt_id: str) -> WindowResearchAdmission:
    """Frozen-summary policy evaluation only; no source/authority/strategy replay assertion."""
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_BYTES:
        raise ValueError("WINDOW_ADMISSION_RECEIPT_BYTE_BOUND")
    if (
        not publication.bundle.pin(expected_receipt_id)
        or publication.bundle.sha(raw) != expected_receipt_id
    ):
        raise ValueError("WINDOW_ADMISSION_RECEIPT_CHECKSUM")
    try:
        doc = json.loads(raw)
        result = _evaluate(doc["frozen_input_json"])
        if encode_window_admission(result) != raw:
            raise ValueError("WINDOW_ADMISSION_RESULT_MISMATCH")
        return result
    except (KeyError, TypeError, UnicodeError, RecursionError, OverflowError):
        raise ValueError("WINDOW_ADMISSION_MALFORMED_RECEIPT") from None
