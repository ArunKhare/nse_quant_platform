"""Retained naive-wall decision evidence and claimed availability, never native admission."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from nse_quant.data_platform import legacy_daily_rv as primitives

VERSION = "legacy-decision-evidence-snapshot@1"
PROJECTION_VERSION = "legacy-decision-evidence-observation@1"
TABLE = "decision_evidence"
SCHEMA = (
    ("evidence_id", "VARCHAR"),
    ("run_id", "VARCHAR"),
    ("ts", "TIMESTAMP"),
    ("symbol", "VARCHAR"),
    ("plugin", "VARCHAR"),
    ("available", "BOOLEAN"),
    ("payload_json", "VARCHAR"),
)
NATURAL_KEY = (1, 2, 3, 4)
MAX_ROWS = 1000
MAX_CELL = 65536
MAX_BYTES = 1048576
MAX_RECORD = 524288
MAX_RECORDS = 4194304
DEFINITION = (
    VERSION,
    PROJECTION_VERSION,
    SCHEMA,
    NATURAL_KEY,
    MAX_ROWS,
    MAX_CELL,
    MAX_BYTES,
    MAX_RECORD,
    MAX_RECORDS,
    "TIMESTAMP wall fields; no timezone assignment or instant",
    "exact stored bool and opaque TEXT; no independent availability or decision replay",
)
Rejected = primitives.Rejected
canonical = primitives.canonical
sha = primitives.sha
pin = primitives.pin
label = primitives.label
parse = primitives.parse


@dataclass(frozen=True)
class Snapshot:
    snapshot_id: str
    payload: bytes
    row_count: int


def wall_fields(value: object) -> str:
    """Preserve SQL TIMESTAMP calendar/clock fields; deliberately not an instant codec."""
    if type(value) is not datetime or value.tzinfo is not None:
        raise Rejected("NAIVE_STORED_WALL_FIELDS_REQUIRED")
    return value.isoformat(timespec="microseconds")


def encode_cell(value: object, kind: str) -> object:
    if value is None:
        raise Rejected("NON_NULL_STORED_EVIDENCE_CELL_REQUIRED")
    if kind == "TIMESTAMP":
        return wall_fields(value)
    if kind == "BOOLEAN":
        if type(value) is not bool:
            raise Rejected("EXACT_STORED_BOOLEAN_REQUIRED")
        return value
    if kind != "VARCHAR" or type(value) is not str or len(value.encode()) > MAX_CELL:
        raise Rejected("EXACT_BOUNDED_EVIDENCE_TEXT_REQUIRED")
    return value


def _row(row: object) -> list[Any]:
    if type(row) is not list or len(row) != len(SCHEMA):
        raise Rejected("EXACT_EVIDENCE_ROW_REQUIRED")
    for value, (_name, kind) in zip(row, SCHEMA, strict=True):
        if kind == "TIMESTAMP":
            if type(value) is not str or len(value) != 26:
                raise Rejected("CANONICAL_WALL_FIELD_SPELLING_REQUIRED")
            if wall_fields(datetime.fromisoformat(value)) != value:
                raise Rejected("CANONICAL_WALL_FIELD_SPELLING_REQUIRED")
        else:
            encode_cell(value, kind)
    return row


def make_snapshot(source_label: str, rows: list[list[Any]]) -> Snapshot:
    if not label(source_label):
        raise Rejected("EXPLICIT_SOURCE_LABEL_REQUIRED")
    if type(rows) is not list or not 1 <= len(rows) <= MAX_ROWS:
        raise Rejected("WHOLE_TABLE_ROW_BOUND")
    try:
        checked = [_row(row) for row in rows]
        ids = [row[0] for row in checked]
        keys = [canonical([row[i] for i in NATURAL_KEY]) for row in checked]
        if len(set(ids)) != len(ids) or len(set(keys)) != len(keys):
            raise Rejected("DUPLICATE_PRIMARY_OR_NATURAL_EVIDENCE_KEY")
        raw = canonical(
            dict(
                version=VERSION,
                table=TABLE,
                columns=SCHEMA,
                source_label=source_label,
                rows=sorted(checked, key=lambda row: canonical(row[0])),
            )
        )
        if len(raw) > MAX_BYTES:
            raise Rejected("SNAPSHOT_BYTE_BOUND")
        return Snapshot(sha(raw), raw, len(rows))
    except Rejected:
        raise
    except (ValueError, TypeError, UnicodeError, OverflowError):
        raise Rejected("MALFORMED_STORED_EVIDENCE_ROW") from None


def replay_snapshot(raw: bytes, *, expected_snapshot_id: str) -> dict[str, Any]:
    doc = parse(raw, MAX_BYTES)
    if not pin(expected_snapshot_id) or sha(raw) != expected_snapshot_id:
        raise Rejected("EXACT_SNAPSHOT_PIN_REQUIRED")
    try:
        if make_snapshot(doc["source_label"], doc["rows"]).payload != raw:
            raise Rejected("COMPLETE_DECISION_EVIDENCE_REPLAY_MISMATCH")
        return doc
    except Rejected:
        raise
    except (ValueError, TypeError, KeyError, RecursionError):
        raise Rejected("DECISION_EVIDENCE_SNAPSHOT_SCHEMA") from None


def derive_records(
    raw: bytes, *, snapshot_id: str, capture_event_id: str, envelope_hash: str
) -> tuple[bytes, ...]:
    if not all(pin(p) for p in (snapshot_id, capture_event_id, envelope_hash)):
        raise Rejected("EXACT_BRONZE_PINS_REQUIRED")
    doc = replay_snapshot(raw, expected_snapshot_id=snapshot_id)
    records = []
    for ordinal, row in enumerate(doc["rows"]):
        fields = dict(zip((n for n, _ in SCHEMA), row, strict=True))
        flags = [
            "EMPTY_OR_WHITESPACE_" + n.upper()
            for n in ("evidence_id", "run_id", "symbol", "plugin")
            if not fields[n].strip()
        ]
        record = canonical(
            dict(
                version=PROJECTION_VERSION,
                source_snapshot_id=snapshot_id,
                source_capture_event_id=capture_event_id,
                source_envelope_hash=envelope_hash,
                source_ordinal=ordinal,
                source_table=TABLE,
                stored_fields=fields,
                flags=flags,
                classification="RETAINED_LEGACY_DECISION_EVIDENCE_NOT_ADMISSION",
                stored_time_semantics="NAIVE_SQL_WALL_FIELDS_TIMEZONE_UNKNOWN",
                stored_ts_instant=None,
                source_timezone=None,
                original_availability_at=None,
                available_semantics="RETAINED_LEGACY_FLAG_NOT_INDEPENDENT_AVAILABILITY",
                payload_interpreted=False,
                original_provider_bytes_retained=False,
                source_revision_history_complete=False,
                native_decision_replayed=False,
                canonical_identity=None,
                economic_validity_at=None,
                publication_asserted=False,
                decision_eligibility_asserted=False,
            )
        )
        if len(record) > MAX_RECORD:
            raise Rejected("EVIDENCE_RECORD_BYTE_BOUND")
        records.append(record)
    if sum(map(len, records)) > MAX_RECORDS:
        raise Rejected("EVIDENCE_AGGREGATE_BYTE_BOUND")
    return tuple(records)
