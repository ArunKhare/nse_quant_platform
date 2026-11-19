"""Bounded retained positions content; never native position truth or execution permission."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

VERSION = "legacy-positions-snapshot@1"
OBSERVATION_VERSION = "legacy-position-observation@1"
TABLE = "positions"
SCHEMA = (
    ("position_id", "VARCHAR"),
    ("strategy_position_id", "VARCHAR"),
    ("proposal_id", "VARCHAR"),
    ("strategy", "VARCHAR"),
    ("underlying", "VARCHAR"),
    ("expiry", "DATE"),
    ("tradingsymbol", "VARCHAR"),
    ("instrument_token", "BIGINT"),
    ("option_type", "VARCHAR"),
    ("strike", "DOUBLE"),
    ("side", "VARCHAR"),
    ("lots", "INTEGER"),
    ("quantity", "INTEGER"),
    ("opened_at", "TIMESTAMP WITH TIME ZONE"),
    ("entry_price", "DOUBLE"),
    ("current_price", "DOUBLE"),
    ("realized_pnl", "DOUBLE"),
    ("unrealized_pnl", "DOUBLE"),
    ("status", "VARCHAR"),
    ("closed_at", "TIMESTAMP WITH TIME ZONE"),
    ("exit_reason", "VARCHAR"),
    ("mark_stale", "BOOLEAN"),
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
    "whole retained base table; position_id only key; all other fields nullable",
    "stored TIMESTAMPTZ instants or unknown; finite binary64 hex; no position truth",
    "no recovered overwritten history, broker truth, fill proof, execution replay or admission",
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


def _invalid(_value: str) -> Any:
    raise Rejected("NONFINITE_POSITION_OUTER_JSON")


def parse(raw: bytes, maximum: int) -> dict[str, Any]:
    if type(raw) is not bytes or not 0 < len(raw) <= maximum:
        raise Rejected("POSITION_CONTENT_BYTE_BOUND")
    try:
        value = json.loads(raw, parse_constant=_invalid)
        if type(value) is not dict or canonical(value) != raw:
            raise Rejected("EXACT_CANONICAL_POSITION_OUTER_OBJECT_REQUIRED")
        return value
    except Rejected:
        raise
    except (TypeError, ValueError, UnicodeError, RecursionError, OverflowError):
        raise Rejected("MALFORMED_POSITION_OUTER_JSON") from None


def encode_cell(value: object, kind: str) -> object:
    if value is None:
        return None
    if kind == "TIMESTAMP WITH TIME ZONE":
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise Rejected("AWARE_STORED_POSITION_INSTANT_REQUIRED")
        return value.astimezone(UTC).isoformat()
    if kind == "DATE":
        if type(value) is not date:
            raise Rejected("EXACT_STORED_POSITION_DATE_REQUIRED")
        return value.isoformat()
    if kind == "DOUBLE":
        if type(value) is not float or value.hex() != value.hex():
            raise Rejected("FINITE_STORED_POSITION_BINARY64_REQUIRED")
        return value.hex()
    if kind in ("BIGINT", "INTEGER"):
        if type(value) is not int or isinstance(value, bool):
            raise Rejected("EXACT_STORED_POSITION_INTEGER_REQUIRED")
        return value
    if kind == "BOOLEAN":
        if type(value) is not bool:
            raise Rejected("EXACT_STORED_POSITION_BOOLEAN_REQUIRED")
        return value
    if kind != "VARCHAR" or type(value) is not str:
        raise Rejected("EXACT_STORED_POSITION_TEXT_REQUIRED")
    try:
        size = len(value.encode())
    except UnicodeError:
        raise Rejected("POSITION_TEXT_ENCODING_INVALID") from None
    if size > MAX_CELL:
        raise Rejected("POSITION_TEXT_CELL_BOUND")
    return value


def _row(row: object) -> list[object]:
    if type(row) is not list or len(row) != len(SCHEMA):
        raise Rejected("EXACT_POSITION_ROW_SCHEMA_REQUIRED")
    checked: list[object] = []
    for original, (_name, kind) in zip(row, SCHEMA, strict=True):
        value = original
        if original is not None and kind == "DATE":
            if type(original) is not str or len(original) != 10:
                raise Rejected("CANONICAL_STORED_POSITION_DATE_REQUIRED")
            value = date.fromisoformat(original)
        elif original is not None and kind == "TIMESTAMP WITH TIME ZONE":
            if type(original) is not str or len(original) > 64:
                raise Rejected("CANONICAL_STORED_POSITION_INSTANT_REQUIRED")
            value = datetime.fromisoformat(original)
        elif original is not None and kind == "DOUBLE":
            if type(original) is not str or len(original) > 64:
                raise Rejected("CANONICAL_STORED_POSITION_BINARY64_REQUIRED")
            value = float.fromhex(original)
        if encode_cell(value, kind) != original:
            raise Rejected("CANONICAL_STORED_POSITION_CELL_REQUIRED")
        checked.append(original)
    if checked[0] is None:
        raise Rejected("POSITION_PRIMARY_KEY_UNKNOWN")
    return checked


@dataclass(frozen=True)
class Snapshot:
    snapshot_id: str
    payload: bytes
    row_count: int


def make_snapshot(source_label: str, rows: list[list[object]]) -> Snapshot:
    if not label(source_label):
        raise Rejected("EXPLICIT_POSITION_SOURCE_LABEL_REQUIRED")
    if type(rows) is not list or not 1 <= len(rows) <= MAX_ROWS:
        raise Rejected("WHOLE_POSITION_TABLE_ROW_BOUND")
    try:
        checked = [_row(row) for row in rows]
        if (
            sum(
                len(value.encode())
                for row in checked
                for index, value in enumerate(row)
                if index not in (5, 13, 19) and isinstance(value, str)
            )
            > MAX_BYTES
        ):
            raise Rejected("POSITION_TEXT_AGGREGATE_BOUND")
        keys = [row[0] for row in checked]
        if len(set(keys)) != len(keys):
            raise Rejected("DUPLICATE_POSITION_PRIMARY_KEY_NO_WINNER")
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
            raise Rejected("POSITION_SNAPSHOT_BYTE_BOUND")
        return Snapshot(sha(raw), raw, len(ordered))
    except Rejected:
        raise
    except (ValueError, TypeError, KeyError, UnicodeError, OverflowError, RecursionError):
        raise Rejected("MALFORMED_RETAINED_POSITION_ROWS") from None


def replay_snapshot(raw: bytes, *, expected_snapshot_id: str) -> dict[str, Any]:
    document = parse(raw, MAX_BYTES)
    if not pin(expected_snapshot_id) or sha(raw) != expected_snapshot_id:
        raise Rejected("EXACT_POSITION_SNAPSHOT_PIN_REQUIRED")
    try:
        if make_snapshot(document["source_label"], document["rows"]).payload != raw:
            raise Rejected("COMPLETE_POSITION_SNAPSHOT_REPLAY_MISMATCH")
        return document
    except Rejected:
        raise
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        raise Rejected("MALFORMED_POSITION_SNAPSHOT_CONTRACT") from None


def derive_records(
    raw: bytes, *, snapshot_id: str, capture_event_id: str, envelope_hash: str
) -> tuple[bytes, ...]:
    if not pin(capture_event_id) or not pin(envelope_hash):
        raise Rejected("EXACT_POSITION_NATIVE_PINS_REQUIRED")
    document = replay_snapshot(raw, expected_snapshot_id=snapshot_id)
    records: list[bytes] = []
    total = 0
    for ordinal, row in enumerate(document["rows"]):
        fields = dict(zip((name for name, _kind in SCHEMA), row, strict=True))
        flags = []
        if fields["closed_at"] is not None and fields["status"] != "CLOSED":
            flags.append("CLOSED_AT_WITHOUT_CLOSED_STATUS")
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
                flags=flags,
                classification="RETAINED_LEGACY_POSITION_NOT_NATIVE_POSITION_TRUTH",
                stored_opened_instant=fields["opened_at"],
                stored_closed_instant=fields["closed_at"],
                source_time_semantics="NULL_OR_LEGACY_STORED_INSTANT_ONLY",
                original_timezone_label=None,
                original_availability_at=None,
                status_semantics="RETAINED_LEGACY_LABEL_NOT_NATIVE_POSITION_TRUTH",
                instrument_identity_authenticated=False,
                mark_stale_interpreted=False,
                pnl_interpreted=False,
                original_provider_bytes_retained=False,
                overwritten_history_recovered=False,
                original_position_execution_replayed=False,
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
            raise Rejected("POSITION_PROJECTION_BYTE_BOUND")
        records.append(record)
    return tuple(records)
