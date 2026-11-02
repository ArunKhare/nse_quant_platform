"""Platform-owned untrusted statement documents: exact content matching, not identity truth."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from typing import Any

VERSION = "underlying-statement-document@1"
PAYLOAD_FORMAT = "underlying_identity_statement_jsonl@1"
MAX_PAYLOAD_BYTES = 1048576
MAX_RECORD_BYTES = 8192
MAX_RECORDS = 256
FIELDS = frozenset(
    {
        "statement_schema",
        "record_id",
        "namespace",
        "external_id",
        "asset_kind",
        "asserted_issuer",
        "assertion",
    }
)


class StatementDocumentRejected(ValueError):
    """Whole-document schema/coverage failure, never an identity rejection."""


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def pin(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def strict_json(raw: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise StatementDocumentRejected("STATEMENT_DOCUMENT_DUPLICATE_JSON_KEY")
            result[key] = value
        return result

    def invalid(_value: str) -> Any:
        raise StatementDocumentRejected("STATEMENT_DOCUMENT_NONFINITE_JSON")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def _identifier(value: object, limit: int) -> bool:
    return (
        isinstance(value, str)
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0," + str(limit - 1) + "}", value)
        is not None
    )


def _fields(
    namespace: str,
    external_id: str,
    asset_kind: str,
    asserted_issuer: str,
    assertion: str,
    record_id: str,
) -> None:
    if (
        not all(
            _identifier(value, limit)
            for value, limit in (
                (namespace, 64),
                (external_id, 256),
                (asserted_issuer, 128),
                (record_id, 64),
            )
        )
        or not isinstance(asset_kind, str)
        or not isinstance(assertion, str)
        or (
            asset_kind not in {"INDEX", "EQUITY"}
            or assertion not in {"ASSERTED", "DISPUTED", "WITHDRAWN"}
        )
    ):
        raise StatementDocumentRejected("STATEMENT_DOCUMENT_FIELD_VALUES_NOT_SUPPORTED")


@dataclass(frozen=True)
class StatementRecord:
    record_id: str
    namespace: str
    external_id: str
    asset_kind: str
    asserted_issuer: str
    assertion: str
    byte_start: int
    byte_end: int
    fragment_sha256: str


@dataclass(frozen=True)
class StatementDocument:
    version: str
    payload_sha256: str
    records: tuple[StatementRecord, ...]


@dataclass(frozen=True)
class StatementExpectation:
    record_id: str
    namespace: str
    external_id: str
    asset_kind: str
    asserted_issuer: str
    assertion: str
    byte_start: int
    byte_end: int
    payload_sha256: str
    fragment_sha256: str

    def __post_init__(self) -> None:
        _fields(
            self.namespace,
            self.external_id,
            self.asset_kind,
            self.asserted_issuer,
            self.assertion,
            self.record_id,
        )
        if (
            type(self.byte_start) is not int
            or type(self.byte_end) is not int
            or not 0 <= self.byte_start < self.byte_end <= MAX_PAYLOAD_BYTES
            or not pin(self.payload_sha256)
            or not pin(self.fragment_sha256)
        ):
            raise ValueError("EXACT_STATEMENT_DOCUMENT_BYTE_PINS_REQUIRED")


@dataclass(frozen=True)
class StatementContentMatch:
    version: str
    status: str
    reason_codes: tuple[str, ...]
    record_id: str
    payload_sha256: str
    same_subject_record_ids: tuple[str, ...] = ()
    record_span_verified: bool = False
    statement_content_matched: bool = False
    evidence_fingerprint: str | None = None
    identity_verified: bool = False
    issuer_authenticated: bool = False
    historical_validity_asserted: bool = False
    availability_evidence_verified: bool = False
    decision_eligibility_asserted: bool = False


def parse_statement_document(raw: bytes) -> StatementDocument:
    """Each record is canonical JSON bytes, LF/CRLF separated; no blank record salvage.

    Offsets exclude line endings and refer to original payload bytes, not characters.
    ALL records validate before selection; record IDs must be unique document-wide.
    """
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_PAYLOAD_BYTES:
        raise StatementDocumentRejected("STATEMENT_DOCUMENT_PAYLOAD_LIMIT_OR_EMPTY")
    rows: list[StatementRecord] = []
    seen: set[str] = set()
    offset = 0
    parts = raw.split(b"\n")
    try:
        for index, part in enumerate(parts):
            terminated = index < len(parts) - 1
            if not part and not terminated and raw.endswith(b"\n"):
                continue
            body = part[:-1] if terminated and part.endswith(b"\r") else part
            if not body or len(body) > MAX_RECORD_BYTES or len(rows) >= MAX_RECORDS:
                raise StatementDocumentRejected("STATEMENT_DOCUMENT_RECORD_LIMIT_OR_BLANK")
            value = strict_json(body.decode("utf-8"))
            if (
                not isinstance(value, dict)
                or set(value) != FIELDS
                or value["statement_schema"] != VERSION
                or canonical(value).encode() != body
            ):
                raise StatementDocumentRejected("STATEMENT_DOCUMENT_SCHEMA_OR_CANONICAL_MISMATCH")
            _fields(
                value["namespace"],
                value["external_id"],
                value["asset_kind"],
                value["asserted_issuer"],
                value["assertion"],
                value["record_id"],
            )
            if value["record_id"] in seen:
                raise StatementDocumentRejected("STATEMENT_DOCUMENT_DUPLICATE_RECORD_ID")
            seen.add(value["record_id"])
            rows.append(
                StatementRecord(
                    value["record_id"],
                    value["namespace"],
                    value["external_id"],
                    value["asset_kind"],
                    value["asserted_issuer"],
                    value["assertion"],
                    offset,
                    offset + len(body),
                    sha(body),
                )
            )
            offset += len(part) + (1 if terminated else 0)
    except StatementDocumentRejected:
        raise
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError):
        raise StatementDocumentRejected("STATEMENT_DOCUMENT_MALFORMED") from None
    return StatementDocument(VERSION, sha(raw), tuple(rows))


def match_statement_content(raw: bytes, *, expected: StatementExpectation) -> StatementContentMatch:
    if not isinstance(expected, StatementExpectation):
        raise TypeError("TYPED_STATEMENT_EXPECTATION_REQUIRED")
    checked = StatementExpectation(**asdict(expected))
    document = parse_statement_document(raw)
    subject = (checked.namespace, checked.external_id, checked.asset_kind)
    related = tuple(
        sorted(
            record.record_id
            for record in document.records
            if (record.namespace, record.external_id, record.asset_kind) == subject
        )
    )
    selected = next((r for r in document.records if r.record_id == checked.record_id), None)
    status = "review_required"
    reasons: tuple[str, ...]
    if document.payload_sha256 != checked.payload_sha256:
        reasons = ("STATEMENT_DOCUMENT_PAYLOAD_PIN_MISMATCH",)
    elif selected is None:
        reasons = ("STATEMENT_DOCUMENT_EXACT_RECORD_NOT_FOUND",)
    elif len(related) > 1:
        reasons = ("MULTIPLE_SAME_SUBJECT_STATEMENTS_REQUIRE_INDEPENDENT_RESOLUTION",)
    elif canonical(
        (
            selected.namespace,
            selected.external_id,
            selected.asset_kind,
            selected.asserted_issuer,
            selected.assertion,
        )
    ) != canonical(
        (
            checked.namespace,
            checked.external_id,
            checked.asset_kind,
            checked.asserted_issuer,
            checked.assertion,
        )
    ):
        reasons = ("STATEMENT_DOCUMENT_CONTENT_DOES_NOT_MATCH_CLAIM",)
    elif (selected.byte_start, selected.byte_end, selected.fragment_sha256) != (
        checked.byte_start,
        checked.byte_end,
        checked.fragment_sha256,
    ):
        reasons = ("STATEMENT_DOCUMENT_EXACT_RECORD_SPAN_MISMATCH",)
    else:
        status = "matched_unverified_statement_content"
        reasons = ("EXACT_UNTRUSTED_STATEMENT_MATCH",)
    matched = status == "matched_unverified_statement_content"
    fingerprint = sha(
        canonical(
            [
                VERSION,
                document.payload_sha256,
                asdict(checked),
                [asdict(record) for record in document.records],
                reasons,
            ]
        ).encode()
    )
    return StatementContentMatch(
        VERSION,
        status,
        reasons,
        checked.record_id,
        document.payload_sha256,
        related,
        matched,
        matched,
        fingerprint,
    )
