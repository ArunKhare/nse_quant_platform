"""Bounded retained decisions content; never native decision replay or admission."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

VERSION = "legacy-decisions-snapshot@1"
OBSERVATION_VERSION = "legacy-decision-observation@1"
TABLE = "decisions"
SCHEMA = (
    ("decision_id", "VARCHAR"),
    ("ts", "TIMESTAMP WITH TIME ZONE"),
    ("run_id", "VARCHAR"),
    ("decision_type", "VARCHAR"),
    ("proposal_id", "VARCHAR"),
    ("strategy", "VARCHAR"),
    ("underlying", "VARCHAR"),
    ("expiry", "DATE"),
    ("payload", "JSON"),
)
MAX_ROWS = 1000
MAX_CELL = 65536
MAX_BYTES = 1048576
MAX_RECORD = 524288
MAX_RECORDS = 4194304
DEFINITION = (
    VERSION,
    OBSERVATION_VERSION,
    SCHEMA,
    MAX_ROWS,
    MAX_CELL,
    MAX_BYTES,
    MAX_RECORD,
    MAX_RECORDS,
    "whole retained base table; decision_id only key; all other fields nullable",
    "stored TIMESTAMPTZ instant or unknown; DATE is retained calendar date only",
    "opaque payload CAST(JSON AS VARCHAR); SQL NULL distinct from JSON null",
    "no recovered overwritten history, payload interpretation, decision replay or admission",
)
Rejected = ValueError


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def pin(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def label(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value) is not None


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise Rejected("DUPLICATE_DECISION_OUTER_JSON_KEY")
        result[key] = value
    return result


def _invalid(_value: str) -> Any:
    raise Rejected("NONFINITE_DECISION_OUTER_JSON")


def parse(raw: bytes, maximum: int) -> dict[str, Any]:
    if type(raw) is not bytes or not 0 < len(raw) <= maximum:
        raise Rejected("DECISION_CONTENT_BYTE_BOUND")
    try:
        value = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_invalid)
        if type(value) is not dict or canonical(value) != raw:
            raise Rejected("EXACT_CANONICAL_DECISION_OUTER_OBJECT_REQUIRED")
        return value
    except Rejected:
        raise
    except (TypeError, ValueError, UnicodeError, RecursionError, OverflowError):
        raise Rejected("MALFORMED_DECISION_OUTER_JSON") from None


def encode_cell(value: object, kind: str) -> object:
    if value is None:
        return None
    if kind == "TIMESTAMP WITH TIME ZONE":
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise Rejected("AWARE_STORED_DECISION_INSTANT_REQUIRED")
        return value.astimezone(UTC).isoformat()
    if kind == "DATE":
        if type(value) is date:
            return value.isoformat()
        if type(value) is str and len(value) == 10:
            try:
                date.fromisoformat(value)
            except ValueError:
                raise Rejected("CANONICAL_STORED_DECISION_DATE_REQUIRED") from None
            return value
        raise Rejected("CANONICAL_STORED_DECISION_DATE_REQUIRED")
    if kind == "BOOLEAN":
        if type(value) is not bool:
            raise Rejected("EXACT_STORED_DECISION_BOOLEAN_REQUIRED")
        return value
    if kind not in ("VARCHAR", "JSON") or type(value) is not str:
        raise Rejected("EXACT_STORED_DECISION_TEXT_REQUIRED")
    try:
        size = len(value.encode())
    except UnicodeError:
        raise Rejected("DECISION_TEXT_ENCODING_INVALID") from None
    if size > MAX_CELL:
        raise Rejected("DECISION_TEXT_CELL_BOUND")
    return value


def _row(row: object) -> list[object]:
    if type(row) is not list or len(row) != len(SCHEMA):
        raise Rejected("EXACT_DECISION_ROW_SCHEMA_REQUIRED")
    checked: list[object] = []
    for original, (_name, kind) in zip(row, SCHEMA, strict=True):
        value = original
        if original is not None and kind == "TIMESTAMP WITH TIME ZONE":
            if type(original) is not str or len(original) > 64:
                raise Rejected("CANONICAL_STORED_DECISION_INSTANT_REQUIRED")
            value = datetime.fromisoformat(original)
        elif original is not None and kind == "DATE":
            if type(original) is not str or len(original) != 10:
                raise Rejected("CANONICAL_STORED_DECISION_DATE_REQUIRED")
            try:
                value = date.fromisoformat(original)
            except ValueError:
                raise Rejected("CANONICAL_STORED_DECISION_DATE_REQUIRED") from None
        if encode_cell(value, kind) != original:
            raise Rejected("CANONICAL_STORED_DECISION_CELL_REQUIRED")
        checked.append(original)
    if checked[0] is None:
        raise Rejected("DECISION_PRIMARY_KEY_UNKNOWN")
    return checked


@dataclass(frozen=True)
class Snapshot:
    snapshot_id: str
    payload: bytes
    row_count: int


def make_snapshot(source_label: str, rows: list[list[object]]) -> Snapshot:
    if not label(source_label):
        raise Rejected("EXPLICIT_DECISION_SOURCE_LABEL_REQUIRED")
    if type(rows) is not list or not 1 <= len(rows) <= MAX_ROWS:
        raise Rejected("WHOLE_DECISION_TABLE_ROW_BOUND")
    try:
        checked = [_row(row) for row in rows]
        if (
            sum(
                len(value.encode())
                for row in checked
                for index, value in enumerate(row)
                if index not in (1, 7) and isinstance(value, str)
            )
            > MAX_BYTES
        ):
            raise Rejected("DECISION_TEXT_AGGREGATE_BOUND")
        keys = [row[0] for row in checked]
        if len(set(keys)) != len(keys):
            raise Rejected("DUPLICATE_DECISION_PRIMARY_KEY_NO_WINNER")
        ordered = sorted(checked, key=lambda row: canonical(row[0]))
        raw = canonical(
            dict(
                version=VERSION,
                table=TABLE,
                source_label=source_label,
                schema=SCHEMA,
                rows=ordered,
            )
        )
        if len(raw) > MAX_BYTES:
            raise Rejected("DECISION_SNAPSHOT_BYTE_BOUND")
        return Snapshot(sha(raw), raw, len(ordered))
    except Rejected:
        raise
    except (ValueError, TypeError, KeyError, UnicodeError, OverflowError, RecursionError):
        raise Rejected("MALFORMED_RETAINED_DECISION_ROWS") from None


def replay_snapshot(raw: bytes, *, expected_snapshot_id: str) -> dict[str, Any]:
    document = parse(raw, MAX_BYTES)
    if not pin(expected_snapshot_id) or sha(raw) != expected_snapshot_id:
        raise Rejected("EXACT_DECISION_SNAPSHOT_PIN_REQUIRED")
    try:
        if make_snapshot(document["source_label"], document["rows"]).payload != raw:
            raise Rejected("COMPLETE_DECISION_SNAPSHOT_REPLAY_MISMATCH")
        return document
    except Rejected:
        raise
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        raise Rejected("MALFORMED_DECISION_SNAPSHOT_CONTRACT") from None


def derive_records(
    raw: bytes, *, snapshot_id: str, capture_event_id: str, envelope_hash: str
) -> tuple[bytes, ...]:
    if not pin(capture_event_id) or not pin(envelope_hash):
        raise Rejected("EXACT_DECISION_NATIVE_PINS_REQUIRED")
    document = replay_snapshot(raw, expected_snapshot_id=snapshot_id)
    records: list[bytes] = []
    total = 0
    for ordinal, row in enumerate(document["rows"]):
        fields = dict(zip((name for name, _kind in SCHEMA), row, strict=True))
        record = canonical(
            dict(
                version=OBSERVATION_VERSION,
                source_label=document["source_label"],
                snapshot_id=snapshot_id,
                capture_event_id=capture_event_id,
                envelope_hash=envelope_hash,
                source_ordinal=ordinal,
                stored_key=[row[0]],
                stored_fields=fields,
                classification="RETAINED_LEGACY_DECISION_NOT_NATIVE_ADMISSION",
                stored_ts_instant=fields["ts"],
                source_time_semantics="NULL_OR_LEGACY_STORED_INSTANT_ONLY",
                original_timezone_label=None,
                original_availability_at=None,
                decision_type_semantics="RETAINED_LEGACY_LABEL_NOT_NATIVE_DECISION_SEMANTICS",
                payload_interpreted=False,
                payload_json_revalidated=False,
                original_provider_bytes_retained=False,
                overwritten_history_recovered=False,
                original_decision_execution_replayed=False,
                native_decision_replayed=False,
                canonical_contract_id=None,
                availability_evidence_verified=False,
                economic_validity_verified=False,
                publication_asserted=False,
                decision_eligibility_asserted=False,
            )
        )
        total += len(record)
        if len(record) > MAX_RECORD or total > MAX_RECORDS:
            raise Rejected("DECISION_PROJECTION_BYTE_BOUND")
        records.append(record)
    return tuple(records)
