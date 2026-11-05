"""Bounded retained gate_results content; passed is a legacy claim, never native permission."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

VERSION = "legacy-gate-results-snapshot@1"
OBSERVATION_VERSION = "legacy-gate-result-observation@1"
TABLE = "gate_results"
SCHEMA = (
    ("gate_result_id", "VARCHAR"),
    ("ts", "TIMESTAMP WITH TIME ZONE"),
    ("run_id", "VARCHAR"),
    ("proposal_id", "VARCHAR"),
    ("strategy", "VARCHAR"),
    ("gate", "VARCHAR"),
    ("passed", "BOOLEAN"),
    ("reason", "VARCHAR"),
    ("details", "JSON"),
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
    "whole retained base table, gate_result_id only key; all other fields nullable",
    "stored TIMESTAMPTZ instant or unknown; exact nullable boolean is not native gate approval",
    "opaque reason TEXT and CAST(details AS VARCHAR); SQL NULL distinct from JSON null",
    "no recovered overwritten history, payload interpretation, gate execution or native admission",
)


class Rejected(ValueError):
    """Fixed codes only; source SQL/operational errors propagate."""


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
    for k, v in items:
        if k in result:
            raise Rejected("DUPLICATE_GATE_OUTER_JSON_KEY")
        result[k] = v
    return result


def _invalid(_value: str) -> Any:
    raise Rejected("NONFINITE_GATE_OUTER_JSON")


def parse(raw: bytes, maximum: int) -> dict[str, Any]:
    if type(raw) is not bytes or not 0 < len(raw) <= maximum:
        raise Rejected("GATE_CONTENT_BYTE_BOUND")
    try:
        value = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_invalid)
        if type(value) is not dict or canonical(value) != raw:
            raise Rejected("EXACT_CANONICAL_GATE_OUTER_OBJECT_REQUIRED")
        return value
    except Rejected:
        raise
    except (TypeError, ValueError, UnicodeError, RecursionError, OverflowError):
        raise Rejected("MALFORMED_GATE_OUTER_JSON") from None


def encode_cell(value: object, kind: str) -> object:
    if value is None:
        return None
    if kind == "TIMESTAMP WITH TIME ZONE":
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise Rejected("AWARE_STORED_GATE_INSTANT_REQUIRED")
        return value.astimezone(UTC).isoformat()
    if kind == "BOOLEAN":
        if type(value) is not bool:
            raise Rejected("EXACT_NULLABLE_STORED_GATE_BOOLEAN_REQUIRED")
        return value
    if kind not in ("VARCHAR", "JSON") or type(value) is not str:
        raise Rejected("EXACT_STORED_GATE_TEXT_REQUIRED")
    try:
        size = len(value.encode())
    except UnicodeError:
        raise Rejected("GATE_TEXT_ENCODING_INVALID") from None
    if size > MAX_CELL:
        raise Rejected("GATE_TEXT_CELL_BOUND")
    return value


def _row(row: object) -> list[object]:
    if type(row) is not list or len(row) != len(SCHEMA):
        raise Rejected("EXACT_GATE_ROW_SCHEMA_REQUIRED")
    checked: list[object] = []
    for original, (_name, kind) in zip(row, SCHEMA, strict=True):
        value = original
        if original is not None and kind == "TIMESTAMP WITH TIME ZONE":
            if type(original) is not str or len(original) > 64:
                raise Rejected("CANONICAL_STORED_GATE_INSTANT_REQUIRED")
            value = datetime.fromisoformat(original)
        if encode_cell(value, kind) != original:
            raise Rejected("CANONICAL_STORED_GATE_CELL_REQUIRED")
        checked.append(original)
    if checked[0] is None:
        raise Rejected("GATE_RESULT_PRIMARY_KEY_UNKNOWN")
    return checked


@dataclass(frozen=True)
class Snapshot:
    snapshot_id: str
    payload: bytes
    row_count: int


def make_snapshot(source_label: str, rows: list[list[object]]) -> Snapshot:
    if not label(source_label):
        raise Rejected("EXPLICIT_GATE_SOURCE_LABEL_REQUIRED")
    if type(rows) is not list or not 1 <= len(rows) <= MAX_ROWS:
        raise Rejected("WHOLE_GATE_TABLE_ROW_BOUND")
    try:
        checked = [_row(r) for r in rows]
        if (
            sum(
                len(v.encode())
                for r in checked
                for i, v in enumerate(r)
                if i not in (1, 6) and isinstance(v, str)
            )
            > MAX_BYTES
        ):
            raise Rejected("GATE_TEXT_AGGREGATE_BOUND")
        keys = [r[0] for r in checked]
        if len(set(keys)) != len(keys):
            raise Rejected("DUPLICATE_GATE_PRIMARY_KEY_NO_WINNER")
        ordered = sorted(checked, key=lambda r: canonical(r[0]))
        raw = canonical(
            dict(
                version=VERSION, table=TABLE, source_label=source_label, schema=SCHEMA, rows=ordered
            )
        )
        if len(raw) > MAX_BYTES:
            raise Rejected("GATE_SNAPSHOT_BYTE_BOUND")
        return Snapshot(sha(raw), raw, len(ordered))
    except Rejected:
        raise
    except (ValueError, TypeError, KeyError, UnicodeError, OverflowError, RecursionError):
        raise Rejected("MALFORMED_RETAINED_GATE_ROWS") from None


def replay_snapshot(raw: bytes, *, expected_snapshot_id: str) -> dict[str, Any]:
    doc = parse(raw, MAX_BYTES)
    if not pin(expected_snapshot_id) or sha(raw) != expected_snapshot_id:
        raise Rejected("EXACT_GATE_SNAPSHOT_PIN_REQUIRED")
    try:
        if make_snapshot(doc["source_label"], doc["rows"]).payload != raw:
            raise Rejected("COMPLETE_GATE_SNAPSHOT_REPLAY_MISMATCH")
    except Rejected:
        raise
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        raise Rejected("MALFORMED_GATE_SNAPSHOT_CONTRACT") from None
    return doc


def derive_records(
    raw: bytes, *, snapshot_id: str, capture_event_id: str, envelope_hash: str
) -> tuple[bytes, ...]:
    if not pin(capture_event_id) or not pin(envelope_hash):
        raise Rejected("EXACT_GATE_NATIVE_PINS_REQUIRED")
    doc = replay_snapshot(raw, expected_snapshot_id=snapshot_id)
    result: list[bytes] = []
    total = 0
    for ordinal, row in enumerate(doc["rows"]):
        fields = dict(zip((n for n, _kind in SCHEMA), row, strict=True))
        record = canonical(
            dict(
                version=OBSERVATION_VERSION,
                source_label=doc["source_label"],
                snapshot_id=snapshot_id,
                capture_event_id=capture_event_id,
                envelope_hash=envelope_hash,
                source_ordinal=ordinal,
                stored_key=[row[0]],
                stored_fields=fields,
                classification="RETAINED_LEGACY_GATE_RESULT_NOT_NATIVE_APPROVAL",
                stored_ts_instant=fields["ts"],
                source_time_semantics="NULL_OR_LEGACY_STORED_INSTANT_ONLY",
                original_timezone_label=None,
                original_availability_at=None,
                passed_semantics="NULLABLE_RETAINED_LEGACY_CLAIM_NOT_NATIVE_GATE_APPROVAL",
                reason_interpreted=False,
                details_interpreted=False,
                details_json_revalidated=False,
                original_provider_bytes_retained=False,
                overwritten_history_recovered=False,
                original_gate_execution_replayed=False,
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
            raise Rejected("GATE_PROJECTION_BYTE_BOUND")
        result.append(record)
    return tuple(result)
