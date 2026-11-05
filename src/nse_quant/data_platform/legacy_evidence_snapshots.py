"""Exact retained evidence_snapshots content; opaque stored JSON text, not admission."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

VERSION = "legacy-evidence-snapshot-table@1"
OBSERVATION_VERSION = "legacy-evidence-snapshot-observation@1"
TABLE = "evidence_snapshots"
SCHEMA = (
    ("run_id", "VARCHAR"),
    ("ts", "TIMESTAMP WITH TIME ZONE"),
    ("symbol", "VARCHAR"),
    ("plugin_name", "VARCHAR"),
    ("payload_json", "JSON"),
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
    "whole retained base table; unique run_id/ts/plugin_name, independent of nullable symbol",
    "stored TIMESTAMPTZ instant UTC-normalized, not original availability/decision time proof",
    "nullable opaque CAST(JSON AS VARCHAR) text; SQL NULL distinct from JSON null",
    "no payload interpretation, writer transformation, history or native decision replay",
)


class Rejected(ValueError):
    """Fixed validation codes; SQL/operational source errors propagate."""


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
            raise Rejected("DUPLICATE_OUTER_JSON_KEY")
        result[key] = value
    return result


def _invalid(_value: str) -> Any:
    raise Rejected("NONFINITE_OUTER_JSON")


def parse(raw: bytes, maximum: int) -> dict[str, Any]:
    if type(raw) is not bytes or not 0 < len(raw) <= maximum:
        raise Rejected("EVIDENCE_SNAPSHOT_BYTE_BOUND")
    try:
        value = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_invalid)
        if type(value) is not dict or canonical(value) != raw:
            raise Rejected("EXACT_CANONICAL_OUTER_OBJECT_REQUIRED")
        return value
    except Rejected:
        raise
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        raise Rejected("MALFORMED_OUTER_EVIDENCE_SNAPSHOT") from None


def encode_cell(value: object, kind: str) -> object:
    if value is None:
        return None
    if kind == "TIMESTAMP WITH TIME ZONE":
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise Rejected("AWARE_STORED_SNAPSHOT_TIMESTAMP_REQUIRED")
        return value.astimezone(UTC).isoformat()
    if kind not in ("VARCHAR", "JSON") or type(value) is not str:
        raise Rejected("EXACT_STORED_TEXT_CELL_REQUIRED")
    try:
        size = len(value.encode())
    except UnicodeError:
        raise Rejected("STORED_TEXT_ENCODING_INVALID") from None
    if size > MAX_CELL:
        raise Rejected("STORED_TEXT_CELL_BOUND")
    return value


def _checked_row(row: object) -> list[object]:
    if type(row) is not list or len(row) != len(SCHEMA):
        raise Rejected("EXACT_EVIDENCE_SNAPSHOT_ROW_SCHEMA_REQUIRED")
    result: list[object] = []
    for original, (_field, kind) in zip(row, SCHEMA, strict=True):
        value = original
        if kind == "TIMESTAMP WITH TIME ZONE" and original is not None:
            if type(original) is not str or len(original) > 64:
                raise Rejected("CANONICAL_STORED_SNAPSHOT_INSTANT_REQUIRED")
            value = datetime.fromisoformat(original)
        if encode_cell(value, kind) != original:
            raise Rejected("CANONICAL_STORED_SNAPSHOT_CELL_REQUIRED")
        result.append(original)
    if any(result[i] is None for i in (0, 1, 3)):
        raise Rejected("EVIDENCE_SNAPSHOT_KEY_UNKNOWN")
    return result


@dataclass(frozen=True)
class Snapshot:
    snapshot_id: str
    payload: bytes
    row_count: int


def make_snapshot(source_label: str, rows: list[list[object]]) -> Snapshot:
    if not label(source_label):
        raise Rejected("EXPLICIT_EVIDENCE_SNAPSHOT_SOURCE_LABEL_REQUIRED")
    if type(rows) is not list or not 1 <= len(rows) <= MAX_ROWS:
        raise Rejected("WHOLE_EVIDENCE_SNAPSHOT_ROW_BOUND")
    try:
        checked = [_checked_row(row) for row in rows]
        text_total = sum(
            len(v.encode())
            for r in checked
            for i, v in enumerate(r)
            if i != 1 and isinstance(v, str)
        )
        if text_total > MAX_BYTES:
            raise Rejected("EVIDENCE_SNAPSHOT_TEXT_AGGREGATE_BOUND")
        keys = [canonical([r[0], r[1], r[3]]) for r in checked]
        if len(set(keys)) != len(keys):
            raise Rejected("DUPLICATE_EVIDENCE_SNAPSHOT_KEY_NO_WINNER")
        ordered = [row for _key, row in sorted(zip(keys, checked, strict=True), key=lambda x: x[0])]
        raw = canonical(
            dict(
                version=VERSION, source_label=source_label, table=TABLE, schema=SCHEMA, rows=ordered
            )
        )
        if len(raw) > MAX_BYTES:
            raise Rejected("EVIDENCE_SNAPSHOT_BYTE_BOUND")
        return Snapshot(sha(raw), raw, len(ordered))
    except Rejected:
        raise
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError, UnicodeError):
        raise Rejected("MALFORMED_EVIDENCE_SNAPSHOT_ROWS") from None


def replay_snapshot(raw: bytes, *, expected_snapshot_id: str) -> dict[str, Any]:
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_BYTES:
        raise Rejected("EVIDENCE_SNAPSHOT_BYTE_BOUND")
    if not pin(expected_snapshot_id) or sha(raw) != expected_snapshot_id:
        raise Rejected("EXACT_EVIDENCE_SNAPSHOT_PIN_REQUIRED")
    doc = parse(raw, MAX_BYTES)
    try:
        rebuilt = make_snapshot(doc["source_label"], doc["rows"])
        if rebuilt.payload != raw:
            raise Rejected("COMPLETE_EVIDENCE_SNAPSHOT_REPLAY_MISMATCH")
    except Rejected:
        raise
    except (TypeError, KeyError, ValueError, OverflowError, RecursionError):
        raise Rejected("MALFORMED_EVIDENCE_SNAPSHOT_CONTRACT") from None
    return doc


def derive_records(
    raw: bytes, *, snapshot_id: str, capture_event_id: str, envelope_hash: str
) -> tuple[bytes, ...]:
    if not pin(capture_event_id) or not pin(envelope_hash):
        raise Rejected("EXACT_EVIDENCE_SNAPSHOT_NATIVE_PINS_REQUIRED")
    doc = replay_snapshot(raw, expected_snapshot_id=snapshot_id)
    result: list[bytes] = []
    total = 0
    for ordinal, row in enumerate(doc["rows"]):
        fields = {n: v for (n, _kind), v in zip(SCHEMA, row, strict=True)}
        record = canonical(
            dict(
                version=OBSERVATION_VERSION,
                source_label=doc["source_label"],
                snapshot_id=snapshot_id,
                capture_event_id=capture_event_id,
                envelope_hash=envelope_hash,
                source_ordinal=ordinal,
                stored_key=[row[0], row[1], row[3]],
                stored_fields=fields,
                classification="RETAINED_LEGACY_EVIDENCE_SNAPSHOT_NOT_ADMISSION",
                stored_ts_instant=fields["ts"],
                source_time_semantics="LEGACY_STORED_INSTANT_ONLY",
                original_timezone_label=None,
                original_availability_at=None,
                canonical_contract_id=None,
                payload_interpreted=False,
                payload_json_validation_reperformed=False,
                original_provider_bytes_retained=False,
                overwritten_history_recovered=False,
                native_decision_replayed=False,
                availability_evidence_verified=False,
                economic_validity_verified=False,
                publication_asserted=False,
                decision_eligibility_asserted=False,
            )
        )
        total += len(record)
        if len(record) > MAX_RECORD or total > MAX_RECORDS:
            raise Rejected("EVIDENCE_SNAPSHOT_RECORD_BYTE_BOUND")
        result.append(record)
    return tuple(result)
