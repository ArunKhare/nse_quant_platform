"""Purpose-aware admission receipts and deterministic policy replay. No trade permission."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from nse_quant.data_platform.feature_bundle import decode_quote_bundle, valid_pin
from nse_quant.data_platform.quote_publication_reader import read_research_publication

POLICY_VERSION = "research-publication-admission@1"
INPUT_VERSION = "publication-admission-input@1"
ARCHIVED_RESEARCH = "ARCHIVED_RESEARCH_ANALYSIS"
POINT_IN_TIME = "POINT_IN_TIME_DECISION"
MAX_INPUT_BYTES = 8_388_608
MAX_RECEIPT_BYTES = 16_777_216
DEFINITION = (
    POLICY_VERSION,
    "input:research-quote-publication-consumer@1 / quote-feature-bundle@1",
    "archival research requires no as-of or economic-time request",
    "RESEARCH_ONLY never admits point-in-time decisions",
    "publication record and audit clocks are not availability evidence",
    "unknown availability/economic validity/contract identity remain unknown",
    "decision eligibility and replay authenticity are never asserted",
)


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


DEFINITION_FINGERPRINT = _hash(_canonical(DEFINITION).encode())


def _json(raw: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("DUPLICATE_ADMISSION_JSON_KEY")
            result[key] = value
        return result

    def invalid(_value: str) -> Any:
        raise ValueError("NONFINITE_ADMISSION_JSON")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def _clock(value: datetime | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("AWARE_ADMISSION_REQUEST_TIME_REQUIRED")
    return value.astimezone(UTC).isoformat()


@dataclass(frozen=True)
class AdmissionRequest:
    use_case: str
    knowledge_cutoff: datetime | None = None
    economic_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.use_case not in {ARCHIVED_RESEARCH, POINT_IN_TIME}:
            raise ValueError("EXPLICIT_SUPPORTED_ADMISSION_USE_CASE_REQUIRED")
        _clock(self.knowledge_cutoff)
        _clock(self.economic_at)
        if self.use_case == ARCHIVED_RESEARCH and (
            self.knowledge_cutoff is not None or self.economic_at is not None
        ):
            raise ValueError("ARCHIVAL_RESEARCH_IS_NOT_AN_ASOF_REQUEST")
        if self.use_case == POINT_IN_TIME and (
            self.knowledge_cutoff is None or self.economic_at is None
        ):
            raise ValueError("BOTH_POINT_IN_TIME_AXES_REQUIRED")


@dataclass(frozen=True)
class AdmissionReceipt:
    receipt_id: str
    policy_version: str
    definition_fingerprint: str
    input_sha256: str
    frozen_input_json: str
    publication_id: str
    bundle_id: str | None
    source_evidence_fingerprint: str | None
    status: str
    reason_codes: tuple[str, ...]
    research_analysis_permitted: bool = False
    decision_eligibility_asserted: bool = False
    availability_evidence_verified: bool = False
    economic_validity_verified: bool = False
    source_current_checked: bool = False
    replay_authenticity_asserted: bool = False


_SOURCE_FIELDS = frozenset(
    {
        "reader_version",
        "publication_id",
        "status",
        "reason_code",
        "purpose",
        "bundle_id",
        "publication_recorded_at",
        "origin_audit_success_recorded_at",
        "clock_semantics",
        "successful_attempt_job_ids",
        "bundle",
        "evidence_fingerprint",
        "research_publication_verified",
        "availability_time_known",
        "source_current_checked",
        "historical_validity_asserted",
        "decision_eligibility_asserted",
    }
)


def _source_reason(source: object, publication_id: str) -> str | None:
    if not isinstance(source, dict) or set(source) != _SOURCE_FIELDS:
        return "PUBLICATION_READER_CONTRACT_MISMATCH"
    if source["reader_version"] != "research-quote-publication-consumer@1":
        return "UNSUPPORTED_PUBLICATION_READER_VERSION"
    if source["publication_id"] != publication_id:
        return "PUBLICATION_PIN_MISMATCH"
    if not isinstance(source["reason_code"], str) or not re.fullmatch(
        r"[A-Z0-9_]{1,128}", source["reason_code"]
    ):
        return "PUBLICATION_READER_CONTRACT_MISMATCH"
    if (
        source["status"] != "verified_research_snapshot"
        or source["research_publication_verified"] is not True
    ):
        return "PUBLICATION_SNAPSHOT_NOT_VERIFIED"
    if (
        source["purpose"] != "RESEARCH_ONLY"
        or source["reason_code"] != "ARCHIVED_CONTENT_AND_PUBLICATION_AUDITS_VERIFIED"
        or not valid_pin(source["bundle_id"])
        or not valid_pin(source["evidence_fingerprint"])
        or any(
            source[key] is not False
            for key in (
                "availability_time_known",
                "source_current_checked",
                "historical_validity_asserted",
                "decision_eligibility_asserted",
            )
        )
        or source["clock_semantics"] != "PLATFORM_RECORD_CLOCK_NOT_PROVIDER_OR_ECONOMIC_VALIDITY"
    ):
        return "RESEARCH_PUBLICATION_CONTRACT_MISMATCH"
    jobs = source["successful_attempt_job_ids"]
    if (
        not isinstance(jobs, list)
        or not 1 <= len(jobs) <= 1000
        or any(
            not isinstance(job, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", job)
            for job in jobs
        )
        or len(set(jobs)) != len(jobs)
    ):
        return "PUBLICATION_ATTEMPT_EVIDENCE_MISSING"
    for key in ("publication_recorded_at", "origin_audit_success_recorded_at"):
        try:
            value = source[key]
            if not isinstance(value, str) or _clock(datetime.fromisoformat(value)) != value:
                return "PUBLICATION_CLOCK_CONTRACT_MISMATCH"
        except (ValueError, TypeError, OverflowError):
            return "PUBLICATION_CLOCK_CONTRACT_MISMATCH"
    nested = source["bundle"]
    try:
        if not isinstance(nested, dict) or nested.get("bundle_id") != source["bundle_id"]:
            return "PUBLICATION_BUNDLE_CONTRACT_MISMATCH"
        manifest = dict(nested)
        del manifest["bundle_id"]
        decode_quote_bundle(_canonical(manifest).encode(), expected_bundle_id=source["bundle_id"])
    except (ValueError, TypeError, KeyError, RecursionError):
        return "PUBLICATION_BUNDLE_CONTRACT_MISMATCH"
    identity = _hash(
        _canonical(
            [
                ["research-quote-publication@1", "research-only-publication-policy@1"],
                source["bundle_id"],
                "RESEARCH_ONLY",
            ]
        ).encode()
    )
    return None if identity == publication_id else "PUBLICATION_IDENTITY_MISMATCH"


def _request_dict(request: AdmissionRequest) -> dict[str, object]:
    return {
        "use_case": request.use_case,
        "knowledge_cutoff": _clock(request.knowledge_cutoff),
        "economic_at": _clock(request.economic_at),
    }


def _request_from_json(value: object) -> AdmissionRequest:
    if not isinstance(value, dict) or set(value) != {"use_case", "knowledge_cutoff", "economic_at"}:
        raise ValueError("ADMISSION_REQUEST_SCHEMA_MISMATCH")
    clocks: dict[str, datetime | None] = {}
    for key in ("knowledge_cutoff", "economic_at"):
        raw = value[key]
        if raw is not None and not isinstance(raw, str):
            raise ValueError("ADMISSION_REQUEST_TIME_SCHEMA_MISMATCH")
        parsed = datetime.fromisoformat(raw) if raw is not None else None
        if _clock(parsed) != raw:
            raise ValueError("CANONICAL_UTC_REQUEST_TIME_REQUIRED")
        clocks[key] = parsed
    return AdmissionRequest(value["use_case"], clocks["knowledge_cutoff"], clocks["economic_at"])


def _payload(receipt: AdmissionReceipt) -> dict[str, object]:
    value = asdict(receipt)
    del value["receipt_id"]
    return value


def _receipt_for_input(frozen: str) -> AdmissionReceipt:
    if len(frozen.encode()) > MAX_INPUT_BYTES:
        raise ValueError("ADMISSION_INPUT_BYTE_LIMIT")
    value = _json(frozen)
    if not isinstance(value, dict) or set(value) != {
        "input_version",
        "publication_id",
        "request",
        "source",
    }:
        raise ValueError("ADMISSION_INPUT_SCHEMA_MISMATCH")
    if value["input_version"] != INPUT_VERSION or _canonical(value) != frozen:
        raise ValueError("UNSUPPORTED_OR_NONCANONICAL_ADMISSION_INPUT")
    pin = value["publication_id"]
    if not valid_pin(pin):
        raise ValueError("EXACT_ADMISSION_PUBLICATION_PIN_REQUIRED")
    request = _request_from_json(value["request"])
    source = value["source"]
    failure = _source_reason(source, pin)
    permitted = False
    status = "REJECTED"
    reasons: tuple[str, ...]
    if failure is not None:
        reasons = (failure,)
    elif request.use_case == ARCHIVED_RESEARCH:
        permitted = True
        status = "ACCEPTED_RESEARCH_ONLY"
        reasons = ("VERIFIED_ARCHIVAL_RESEARCH_SNAPSHOT", "NO_POINT_IN_TIME_CLAIM")
    else:
        reasons = (
            "RESEARCH_ONLY_PURPOSE_NOT_DECISION_INPUT",
            "AVAILABILITY_EVIDENCE_UNKNOWN",
            "PUBLICATION_RECORD_AND_AUDIT_CLOCKS_ARE_NOT_AVAILABILITY_PROOF",
            "ECONOMIC_VALIDITY_EVIDENCE_UNKNOWN",
            "CANONICAL_CONTRACT_IDENTITY_UNKNOWN",
            "DECISION_ELIGIBILITY_NOT_ASSERTED",
        )
    bundle_id = source["bundle_id"] if failure is None else None
    source_fp = source["evidence_fingerprint"] if failure is None else None
    receipt = AdmissionReceipt(
        "",
        POLICY_VERSION,
        DEFINITION_FINGERPRINT,
        _hash(frozen.encode()),
        frozen,
        pin,
        bundle_id,
        source_fp,
        status,
        reasons,
        permitted,
    )
    raw = _canonical(_payload(receipt)).encode()
    if len(raw) > MAX_RECEIPT_BYTES:
        raise ValueError("ADMISSION_RECEIPT_BYTE_LIMIT")
    return AdmissionReceipt(**dict(asdict(receipt), receipt_id=_hash(raw)))


def assess_publication_use(
    publications: Any,
    *,
    publication_id: str,
    request: AdmissionRequest,
) -> AdmissionReceipt:
    """Reverify one archived publication, freeze inputs and evaluate. No writes.

    ACCEPTED_RESEARCH_ONLY is never a trading/decision permit. There is no caller
    override for unknown times, purpose, canonical identity or decision eligibility.
    """
    if not valid_pin(publication_id):
        raise ValueError("EXACT_ADMISSION_PUBLICATION_PIN_REQUIRED")
    if not isinstance(request, AdmissionRequest):
        raise TypeError("TYPED_ADMISSION_REQUEST_REQUIRED")
    evidence = read_research_publication(publications, publication_id=publication_id)
    frozen = _canonical(
        {
            "input_version": INPUT_VERSION,
            "publication_id": publication_id,
            "request": _request_dict(request),
            "source": asdict(evidence),
        }
    )
    return _receipt_for_input(frozen)


def encode_admission_receipt(receipt: AdmissionReceipt) -> bytes:
    """Validate deterministic content, not original source authenticity/authority."""
    expected = _receipt_for_input(receipt.frozen_input_json)
    if _canonical(_payload(receipt)) != _canonical(_payload(expected)) or receipt.receipt_id != (
        expected.receipt_id
    ):
        raise ValueError("ADMISSION_RECEIPT_RESULT_MISMATCH")
    return _canonical(_payload(receipt)).encode()


def replay_admission_receipt(raw: bytes, *, expected_receipt_id: str) -> AdmissionReceipt:
    """Replay this policy from frozen input ONLY. No DB/current-source calls.

    Integrity/reproducibility is not proof of provenance, historical availability,
    authorization or full strategy/decision/execution replay. Nothing is executed.
    """
    if not isinstance(raw, bytes) or len(raw) > MAX_RECEIPT_BYTES:
        raise ValueError("BOUNDED_EXACT_ADMISSION_RECEIPT_BYTES_REQUIRED")
    if not valid_pin(expected_receipt_id) or _hash(raw) != expected_receipt_id:
        raise ValueError("ADMISSION_RECEIPT_CHECKSUM_MISMATCH")
    try:
        value = _json(raw.decode("utf-8"))
        keys = set(AdmissionReceipt.__dataclass_fields__) - {"receipt_id"}
        if not isinstance(value, dict) or set(value) != keys or _canonical(value).encode() != raw:
            raise ValueError("ADMISSION_RECEIPT_SCHEMA_OR_CANONICAL_MISMATCH")
        if not isinstance(value["reason_codes"], list):
            raise ValueError("ADMISSION_REASON_SCHEMA_MISMATCH")
        receipt = AdmissionReceipt(
            **dict(value, reason_codes=tuple(value["reason_codes"]), receipt_id=expected_receipt_id)
        )
        encode_admission_receipt(receipt)
        return receipt
    except (
        UnicodeError,
        TypeError,
        KeyError,
        AttributeError,
        RecursionError,
        OverflowError,
    ) as error:
        raise ValueError("MALFORMED_ADMISSION_RECEIPT") from error
