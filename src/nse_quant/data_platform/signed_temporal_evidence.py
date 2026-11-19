"""Supplied signed temporal declarations, not independently evidenced market-time truth."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

VERSION = "signed-publication-temporal-evidence@1"
DOMAIN = b"nse-quant/publication-temporal-declaration/ed25519/v1\x00"
MAX_DOCUMENT_BYTES = 8192
MAX_RECORD_BYTES = 18432
MAX_RECORDS = 16
MAX_RECORD_TOTAL = 262144
MAX_SUPPORT_BYTES = 65536
MAX_SUPPORT_TOTAL = 262144
MAX_RECEIPT_BYTES = 2097152


class TemporalEvidenceRejected(ValueError):
    """Fixed codes only; operational exceptions are not converted to policy denials."""


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def pin(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _label(value: object) -> bool:
    return (
        type(value) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,63}", value) is not None
    )


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise TemporalEvidenceRejected("TEMPORAL_DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _invalid(_value: str) -> Any:
    raise TemporalEvidenceRejected("TEMPORAL_NONFINITE_JSON")


def parse(raw: bytes, maximum: int) -> dict[str, Any]:
    if type(raw) is not bytes or not 0 < len(raw) <= maximum:
        raise TemporalEvidenceRejected("TEMPORAL_BYTE_BOUND")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_invalid)
        if not isinstance(value, dict) or canonical(value) != raw:
            raise TemporalEvidenceRejected("TEMPORAL_CANONICAL_OBJECT_REQUIRED")
        return value
    except TemporalEvidenceRejected:
        raise
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        raise TemporalEvidenceRejected("TEMPORAL_MALFORMED_JSON") from None


def clock(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise TemporalEvidenceRejected("TEMPORAL_AWARE_REQUEST_TIME_REQUIRED")
    return value.astimezone(UTC).isoformat()


def _instant(value: object) -> datetime | None:
    if value is None:
        return None
    if type(value) is not str or len(value) > 40:
        raise TemporalEvidenceRejected("TEMPORAL_CANONICAL_UTC_DECLARATION_REQUIRED")
    try:
        result = datetime.fromisoformat(value)
        if clock(result) != value:
            raise TemporalEvidenceRejected("TEMPORAL_CANONICAL_UTC_DECLARATION_REQUIRED")
        return result
    except ValueError:
        raise TemporalEvidenceRejected("TEMPORAL_CANONICAL_UTC_DECLARATION_REQUIRED") from None


def _hex(value: object, size: int) -> bytes:
    if type(value) is not str or re.fullmatch(r"[a-f0-9]{" + str(size * 2) + "}", value) is None:
        raise TemporalEvidenceRejected("TEMPORAL_EXACT_HEX_REQUIRED")
    return bytes.fromhex(value)


@dataclass(frozen=True)
class TemporalSubject:
    namespace: str
    asset_kind: str
    publication_id: str
    bundle_id: str
    publication_evidence_fingerprint: str

    def __post_init__(self) -> None:
        if (
            not _label(self.namespace)
            or self.asset_kind not in ("INDEX", "EQUITY")
            or any(
                not pin(x)
                for x in (
                    self.publication_id,
                    self.bundle_id,
                    self.publication_evidence_fingerprint,
                )
            )
        ):
            raise TemporalEvidenceRejected("TEMPORAL_EXACT_SUBJECT_REQUIRED")


@dataclass(frozen=True)
class TemporalRequest:
    knowledge_cutoff: datetime
    economic_at: datetime

    def __post_init__(self) -> None:
        clock(self.knowledge_cutoff)
        clock(self.economic_at)


def signing_message(raw_document: bytes) -> bytes:
    if type(raw_document) is not bytes or not 0 < len(raw_document) <= MAX_DOCUMENT_BYTES:
        raise TemporalEvidenceRejected("TEMPORAL_DOCUMENT_BOUND")
    return DOMAIN + len(raw_document).to_bytes(8, "big") + raw_document


def encode_signed_declaration(raw_document: bytes, signature: bytes) -> bytes:
    parse(raw_document, MAX_DOCUMENT_BYTES)
    if type(signature) is not bytes or len(signature) != 64:
        raise TemporalEvidenceRejected("TEMPORAL_SIGNATURE_SHAPE")
    return canonical(dict(document_hex=raw_document.hex(), signature_hex=signature.hex()))


def declaration_document(record: bytes) -> tuple[bytes, dict[str, Any], bytes]:
    envelope = parse(record, MAX_RECORD_BYTES)
    if set(envelope) != {"document_hex", "signature_hex"}:
        raise TemporalEvidenceRejected("TEMPORAL_ENVELOPE_SCHEMA")
    text = envelope["document_hex"]
    if type(text) is not str or not 0 < len(text) <= MAX_DOCUMENT_BYTES * 2 or len(text) % 2:
        raise TemporalEvidenceRejected("TEMPORAL_DOCUMENT_BOUND")
    raw = _hex(text, len(text) // 2)
    return raw, parse(raw, MAX_DOCUMENT_BYTES), _hex(envelope["signature_hex"], 64)


@dataclass(frozen=True)
class TemporalEvaluation:
    version: str
    status: str
    reason_codes: tuple[str, ...]
    subject: TemporalSubject
    record_sha256s: tuple[str, ...]
    expected_tip_sha256: str
    knowledge_cutoff: str
    economic_at: str
    declared_available_at: str | None
    declared_economic_from: str | None
    declared_economic_until: str | None
    evidence_fingerprint: str
    signed_declaration_constraints_satisfied: bool = False
    declared_time_constraints_satisfied: bool = False
    independent_time_evidence_verified: bool = False
    availability_evidence_verified: bool = False
    economic_validity_verified: bool = False
    issuer_authority_authenticated: bool = False
    history_completeness_verified: bool = False
    authorized_revocation_asserted: bool = False
    identity_verified: bool = False
    historical_validity_asserted: bool = False
    decision_eligibility_asserted: bool = False


def evaluate_temporal_declarations(
    records: tuple[bytes, ...],
    *,
    expected_record_sha256s: tuple[str, ...],
    expected_tip_sha256: str,
    verification_keys: tuple[bytes, ...],
    support_blobs: tuple[bytes, ...],
    subject: TemporalSubject,
    request: TemporalRequest,
) -> TemporalEvaluation:
    """Validate all supplied evidence BEFORE any time filtering; exact pinned tip only.

    Keys supplied here prove possession only; native integration derives them from
    actual lifecycle records. Support bytes are retained claims, not authenticated sources.
    DISPUTE/WITHDRAW permanently block this supplied series: no reactivation/recovery.
    Economic interval is [from, until). Null until is UNKNOWN, never unbounded infinity.
    No ordering is imposed between the independent request axes.
    """
    if (
        type(subject) is not TemporalSubject
        or type(request) is not TemporalRequest
        or type(records) is not tuple
        or not 1 <= len(records) <= MAX_RECORDS
        or type(expected_record_sha256s) is not tuple
        or len(expected_record_sha256s) != len(records)
        or any(not pin(x) for x in expected_record_sha256s)
        or not pin(expected_tip_sha256)
        or type(verification_keys) is not tuple
        or len(verification_keys) != len(records)
        or any(type(k) is not bytes or len(k) != 32 for k in verification_keys)
        or type(support_blobs) is not tuple
        or not 1 <= len(support_blobs) <= 16
    ):
        raise TemporalEvidenceRejected("TEMPORAL_EXACT_BOUNDED_INPUTS_REQUIRED")
    subject = TemporalSubject(**asdict(subject))
    cutoff, economic = clock(request.knowledge_cutoff), clock(request.economic_at)
    if any(type(x) is not bytes or not 0 < len(x) <= MAX_RECORD_BYTES for x in records):
        raise TemporalEvidenceRejected("TEMPORAL_RECORD_BOUND")
    if sum(len(x) for x in records) > MAX_RECORD_TOTAL:
        raise TemporalEvidenceRejected("TEMPORAL_RECORD_AGGREGATE_BOUND")
    if any(type(x) is not bytes or not 0 < len(x) <= MAX_SUPPORT_BYTES for x in support_blobs):
        raise TemporalEvidenceRejected("TEMPORAL_SUPPORT_BOUND")
    if sum(len(x) for x in support_blobs) > MAX_SUPPORT_TOTAL:
        raise TemporalEvidenceRejected("TEMPORAL_SUPPORT_AGGREGATE_BOUND")
    support_pins = tuple(sha(x) for x in support_blobs)
    if len(set(support_pins)) != len(support_pins):
        raise TemporalEvidenceRejected("TEMPORAL_DUPLICATE_SUPPORT")
    previous: str | None = None
    series: str | None = None
    negative = False
    last: dict[str, Any] = {}
    for sequence, (record, expected, key) in enumerate(
        zip(records, expected_record_sha256s, verification_keys, strict=True),
        1,
    ):
        if sha(record) != expected:
            raise TemporalEvidenceRejected("TEMPORAL_RECORD_PIN_MISMATCH")
        raw, value, signature = declaration_document(record)
        if set(value) != {
            "schema",
            "series_id",
            "subject",
            "sequence",
            "predecessor_sha256",
            "lifecycle_tip_sha256",
            "statement_kind",
            "declared_available_at",
            "declared_economic_from",
            "declared_economic_until",
            "support_sha256s",
        }:
            raise TemporalEvidenceRejected("TEMPORAL_DECLARATION_SCHEMA")
        if (
            value["schema"] != VERSION
            or not _label(value["series_id"])
            or value["subject"] != asdict(subject)
            or type(value["sequence"]) is not int
            or value["sequence"] != sequence
            or value["predecessor_sha256"] != previous
            or not pin(value["lifecycle_tip_sha256"])
        ):
            raise TemporalEvidenceRejected("TEMPORAL_SUBJECT_OR_CAUSAL_CHAIN_MISMATCH")
        if series is not None and value["series_id"] != series:
            raise TemporalEvidenceRejected("TEMPORAL_SERIES_MISMATCH")
        if value["statement_kind"] not in ("ASSERT", "DISPUTE", "WITHDRAW"):
            raise TemporalEvidenceRejected("TEMPORAL_STATEMENT_KIND")
        refs = value["support_sha256s"]
        if (
            not isinstance(refs, list)
            or not 1 <= len(refs) <= 16
            or any(not pin(x) for x in refs)
            or len(set(refs)) != len(refs)
            or not set(refs).issubset(support_pins)
        ):
            raise TemporalEvidenceRejected("TEMPORAL_EXACT_SUPPORT_BYTES_REQUIRED")
        _instant(value["declared_available_at"])
        start = _instant(value["declared_economic_from"])
        end = _instant(value["declared_economic_until"])
        if start is not None and end is not None and start >= end:
            raise TemporalEvidenceRejected("TEMPORAL_ECONOMIC_INTERVAL_ORDER")
        try:
            Ed25519PublicKey.from_public_bytes(key).verify(signature, signing_message(raw))
        except InvalidSignature:
            raise TemporalEvidenceRejected("TEMPORAL_SIGNATURE_INVALID") from None
        negative = negative or value["statement_kind"] != "ASSERT"
        series, previous, last = value["series_id"], expected, value
    if previous != expected_tip_sha256:
        raise TemporalEvidenceRejected("TEMPORAL_REVIEWED_TIP_MISMATCH")
    reasons: list[str] = []
    if negative:
        reasons.append("SUPPLIED_SERIES_DISPUTED_OR_WITHDRAWN_NO_REACTIVATION")
    if any(
        last[k] is None
        for k in (
            "declared_available_at",
            "declared_economic_from",
            "declared_economic_until",
        )
    ):
        reasons.append("DECLARED_AVAILABILITY_OR_ECONOMIC_INTERVAL_UNKNOWN")
    if last["declared_available_at"] is not None:
        available_at = _instant(last["declared_available_at"])
        assert available_at is not None
        if available_at > request.knowledge_cutoff:
            reasons.append("DECLARED_AVAILABILITY_AFTER_KNOWLEDGE_CUTOFF")
    start = _instant(last["declared_economic_from"])
    end = _instant(last["declared_economic_until"])
    if start is not None and request.economic_at < start:
        reasons.append("ECONOMIC_AT_BEFORE_DECLARED_INTERVAL")
    if end is not None and request.economic_at >= end:
        reasons.append("ECONOMIC_AT_AT_OR_AFTER_DECLARED_INTERVAL_END")
    matched = not reasons
    if matched:
        reasons.append("SIGNED_DECLARED_TIMES_MATCH_NOT_INDEPENDENT_TIME_PROOF")
    fingerprint = sha(
        canonical(
            [
                VERSION,
                asdict(subject),
                expected_record_sha256s,
                expected_tip_sha256,
                [sha(k) for k in verification_keys],
                support_pins,
                cutoff,
                economic,
                reasons,
            ]
        )
    )
    return TemporalEvaluation(
        VERSION,
        "matched_supplied_declarations" if matched else "review_required",
        tuple(reasons),
        subject,
        expected_record_sha256s,
        expected_tip_sha256,
        cutoff,
        economic,
        last["declared_available_at"],
        last["declared_economic_from"],
        last["declared_economic_until"],
        fingerprint,
        True,
        matched,
    )


def encode_temporal_receipt(
    records: tuple[bytes, ...],
    *,
    expected_record_sha256s: tuple[str, ...],
    expected_tip_sha256: str,
    verification_keys: tuple[bytes, ...],
    support_blobs: tuple[bytes, ...],
    subject: TemporalSubject,
    request: TemporalRequest,
) -> bytes:
    result = evaluate_temporal_declarations(
        records,
        expected_record_sha256s=expected_record_sha256s,
        expected_tip_sha256=expected_tip_sha256,
        verification_keys=verification_keys,
        support_blobs=support_blobs,
        subject=subject,
        request=request,
    )
    raw = canonical(
        dict(
            version=VERSION,
            records_hex=[x.hex() for x in records],
            record_sha256s=expected_record_sha256s,
            tip_sha256=expected_tip_sha256,
            verification_keys_hex=[x.hex() for x in verification_keys],
            support_hex=[x.hex() for x in support_blobs],
            subject=asdict(subject),
            request=dict(
                knowledge_cutoff=clock(request.knowledge_cutoff),
                economic_at=clock(request.economic_at),
            ),
            result=asdict(result),
        )
    )
    if len(raw) > MAX_RECEIPT_BYTES:
        raise TemporalEvidenceRejected("TEMPORAL_RECEIPT_BOUND")
    return raw


def replay_temporal_receipt(raw: bytes, *, expected_receipt_sha256: str) -> TemporalEvaluation:
    """Full original-byte/crypto/result replay only, not native publication/authority replay."""
    value = parse(raw, MAX_RECEIPT_BYTES)
    if not pin(expected_receipt_sha256) or sha(raw) != expected_receipt_sha256:
        raise TemporalEvidenceRejected("TEMPORAL_RECEIPT_PIN_MISMATCH")
    if set(value) != {
        "version",
        "records_hex",
        "record_sha256s",
        "tip_sha256",
        "verification_keys_hex",
        "support_hex",
        "subject",
        "request",
        "result",
    }:
        raise TemporalEvidenceRejected("TEMPORAL_RECEIPT_SCHEMA")
    try:
        if value["version"] != VERSION:
            raise TemporalEvidenceRejected("TEMPORAL_RECEIPT_VERSION")
        for name in ("records_hex", "verification_keys_hex", "record_sha256s", "support_hex"):
            if not isinstance(value[name], list) or not 1 <= len(value[name]) <= 16:
                raise TemporalEvidenceRejected("TEMPORAL_RECEIPT_ARRAY_BOUND")

        def blobs(name: str, limit: int) -> tuple[bytes, ...]:
            result: list[bytes] = []
            for text in value[name]:
                if type(text) is not str or not 0 < len(text) <= limit * 2 or len(text) % 2:
                    raise TemporalEvidenceRejected("TEMPORAL_RECEIPT_HEX_BOUND")
                result.append(_hex(text, len(text) // 2))
            return tuple(result)

        request_value = value["request"]
        if not isinstance(request_value, dict) or set(request_value) != {
            "knowledge_cutoff",
            "economic_at",
        }:
            raise TemporalEvidenceRejected("TEMPORAL_RECEIPT_REQUEST_SCHEMA")
        cutoff = _instant(request_value["knowledge_cutoff"])
        economic = _instant(request_value["economic_at"])
        if cutoff is None or economic is None:
            raise TemporalEvidenceRejected("TEMPORAL_RECEIPT_REQUEST_UNKNOWN")
        args = dict(
            records=blobs("records_hex", MAX_RECORD_BYTES),
            expected_record_sha256s=tuple(value["record_sha256s"]),
            expected_tip_sha256=value["tip_sha256"],
            verification_keys=blobs("verification_keys_hex", 32),
            support_blobs=blobs("support_hex", MAX_SUPPORT_BYTES),
            subject=TemporalSubject(**value["subject"]),
            request=TemporalRequest(cutoff, economic),
        )
        expected = encode_temporal_receipt(**args)
        if raw != expected:
            raise TemporalEvidenceRejected("TEMPORAL_COMPLETE_RECEIPT_REPLAY_MISMATCH")
        return evaluate_temporal_declarations(**args)
    except TemporalEvidenceRejected:
        raise
    except (ValueError, TypeError, KeyError, RecursionError, OverflowError):
        raise TemporalEvidenceRejected("TEMPORAL_RECEIPT_MALFORMED") from None
