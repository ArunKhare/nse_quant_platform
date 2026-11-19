"""Purpose-aware migrated-publication admission; no decision permission or authority."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from nse_quant.data_platform import legacy_market_publication as publication
from nse_quant.data_platform.publication_admission import (
    ARCHIVED_RESEARCH,
    AdmissionRequest,
    _request_dict,
    _request_from_json,
)

VERSION = "legacy-price-research-admission@1"
MAX_BYTES = 32768
DEFINITION = (
    VERSION,
    publication.VERSION,
    publication.POLICY,
    "pinned retained publication and original audit; not current-source validation",
    "archival research only; reject POINT_IN_TIME_DECISION regardless of clocks",
    "frozen summary replay proves policy computation, not source authenticity or authority",
)


@dataclass(frozen=True)
class LegacyResearchAdmission:
    receipt_id: str
    frozen_input_json: str
    status: str
    reason_codes: tuple[str, ...]
    research_analysis_permitted: bool
    policy_version: str = VERSION
    decision_eligibility_asserted: bool = False
    availability_verified: bool = False
    economic_validity_verified: bool = False
    canonical_contract_id: None = None
    source_current_checked: bool = False
    replay_authenticity_asserted: bool = False


def _summary(evidence: publication.LegacyResearchPublication) -> dict[str, object]:
    return dict(
        publication_id=evidence.publication_id,
        recording_fingerprint=evidence.recording_fingerprint,
        bundle_id=evidence.bundle_id,
        gold_build_id=evidence.request.build_id,
        row_count=evidence.row_count,
        purpose=evidence.purpose,
        clock_semantics=evidence.clock_semantics,
        publication_recorded_at=evidence.publication_recorded_at,
        origin_audit_success_recorded_at=evidence.origin_audit_success_recorded_at,
        research_publication_verified=evidence.research_publication_verified,
        current_source_checked=evidence.current_source_checked,
        decision_eligibility_asserted=evidence.decision_eligibility_asserted,
        availability_verified=evidence.availability_verified,
        economic_validity_verified=evidence.economic_validity_verified,
        canonical_contract_id=evidence.canonical_contract_id,
    )


def _evaluate(frozen: str) -> LegacyResearchAdmission:
    if type(frozen) is not str or not 0 < len(frozen.encode()) <= MAX_BYTES:
        raise ValueError("LEGACY_ADMISSION_INPUT_BYTE_BOUND")
    try:
        value = json.loads(frozen)
        if (
            type(value) is not dict
            or set(value) != {"definition", "request", "source"}
            or publication._canonical(value) != frozen
            or value["definition"] != publication._hash(DEFINITION)
        ):
            raise ValueError("LEGACY_ADMISSION_INPUT_CONTRACT")
        request = _request_from_json(value["request"])
        source = value["source"]
        fields = {
            "publication_id",
            "recording_fingerprint",
            "bundle_id",
            "gold_build_id",
            "row_count",
            "purpose",
            "clock_semantics",
            "publication_recorded_at",
            "origin_audit_success_recorded_at",
            "research_publication_verified",
            "current_source_checked",
            "decision_eligibility_asserted",
            "availability_verified",
            "economic_validity_verified",
            "canonical_contract_id",
        }
        if (
            type(source) is not dict
            or set(source) != fields
            or any(
                not publication.bundle.gold.pin(source[k])
                for k in ("publication_id", "recording_fingerprint", "bundle_id", "gold_build_id")
            )
            or source["publication_id"]
            != publication.publication_id(source["gold_build_id"], source["bundle_id"])
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
                )
            )
        ):
            raise ValueError("LEGACY_ADMISSION_SOURCE_SUMMARY_CONTRACT")
        for key in ("publication_recorded_at", "origin_audit_success_recorded_at"):
            clock = source[key]
            if (
                type(clock) is not str
                or publication._instant(datetime.fromisoformat(clock)) != clock
            ):
                raise ValueError("LEGACY_ADMISSION_RECORD_CLOCK_CONTRACT")
    except (TypeError, KeyError, RecursionError, OverflowError):
        raise ValueError("LEGACY_ADMISSION_MALFORMED_INPUT") from None
    permitted = request.use_case == ARCHIVED_RESEARCH
    reasons = (
        ("VERIFIED_RETAINED_RESEARCH_PUBLICATION", "NO_POINT_IN_TIME_CLAIM")
        if permitted
        else (
            "RESEARCH_ONLY_PURPOSE_NOT_DECISION_INPUT",
            "AVAILABILITY_EVIDENCE_UNKNOWN",
            "ECONOMIC_VALIDITY_EVIDENCE_UNKNOWN",
            "CANONICAL_IDENTITY_UNKNOWN",
            "RECORD_CLOCKS_ARE_NOT_AVAILABILITY_PROOF",
            "DECISION_ELIGIBILITY_NOT_ASSERTED",
        )
    )
    receipt = LegacyResearchAdmission(
        "",
        frozen,
        "ACCEPTED_RESEARCH_ONLY" if permitted else "REJECTED",
        reasons,
        permitted,
    )
    return LegacyResearchAdmission(
        **dict(
            asdict(receipt),
            receipt_id=publication._hash(
                {k: v for k, v in asdict(receipt).items() if k != "receipt_id"}
            ),
        )
    )


def assess_legacy_publication_use(
    conn: Any,
    *,
    publication_id: str,
    expected_recording_fingerprint: str,
    request: AdmissionRequest,
) -> LegacyResearchAdmission:
    """Actual pinned retained reader twice. Invalid/operational sources raise, never accept."""
    if type(request) is not AdmissionRequest:
        raise TypeError("TYPED_LEGACY_ADMISSION_REQUEST_REQUIRED")
    request = AdmissionRequest(request.use_case, request.knowledge_cutoff, request.economic_at)
    args = dict(
        publication_id=publication_id, expected_recording_fingerprint=expected_recording_fingerprint
    )
    first = publication.read_legacy_research_publication(conn, **args)
    frozen = publication._canonical(
        dict(
            definition=publication._hash(DEFINITION),
            request=_request_dict(request),
            source=_summary(first),
        )
    )
    if first != publication.read_legacy_research_publication(conn, **args):
        raise ValueError("LEGACY_ADMISSION_PUBLICATION_DRIFT")
    return _evaluate(frozen)


def encode_legacy_admission(receipt: LegacyResearchAdmission) -> bytes:
    if type(receipt) is not LegacyResearchAdmission or receipt != _evaluate(
        receipt.frozen_input_json
    ):
        raise ValueError("LEGACY_ADMISSION_RESULT_MISMATCH")
    raw = publication._canonical(
        {k: v for k, v in asdict(receipt).items() if k != "receipt_id"}
    ).encode()
    if len(raw) > MAX_BYTES:
        raise ValueError("LEGACY_ADMISSION_RECEIPT_BYTE_BOUND")
    return raw


def replay_legacy_admission(raw: bytes, *, expected_receipt_id: str) -> LegacyResearchAdmission:
    """Summary-only policy replay. No DB/source attestation; NEVER decision eligibility."""
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_BYTES:
        raise ValueError("LEGACY_ADMISSION_RECEIPT_BYTE_BOUND")
    if (
        not publication.bundle.gold.pin(expected_receipt_id)
        or publication.bundle.gold.sha(raw) != expected_receipt_id
    ):
        raise ValueError("LEGACY_ADMISSION_RECEIPT_CHECKSUM")
    try:
        value = json.loads(raw)
        if type(value) is not dict:
            raise ValueError("LEGACY_ADMISSION_RECEIPT_CONTRACT")
        result = _evaluate(value["frozen_input_json"])
        if encode_legacy_admission(result) != raw:
            raise ValueError("LEGACY_ADMISSION_RESULT_MISMATCH")
        return result
    except (TypeError, KeyError, UnicodeError, RecursionError, OverflowError):
        raise ValueError("LEGACY_ADMISSION_MALFORMED_RECEIPT") from None
