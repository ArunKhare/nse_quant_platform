"""Layout-explicit retained policy evidence; READY/allowed/risk JSON is not authority."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from nse_quant.data_platform import legacy_daily_rv as primitives
from nse_quant.data_platform import legacy_daily_rv_bronze as common

VERSION = "legacy-regime-policy-snapshot@1"
PROJECTION_VERSION = "legacy-regime-policy-observation@1"
TABLE = "regime_policies"
SCHEMA = (
    ("policy_id", "VARCHAR"),
    ("symbol", "VARCHAR"),
    ("train_start", "DATE"),
    ("train_end", "DATE"),
    ("test_start", "DATE"),
    ("test_end", "DATE"),
    ("allowed_regimes", "JSON"),
    ("regime_metrics", "JSON"),
    ("selection_status", "VARCHAR"),
    ("risk_limits", "JSON"),
    ("created_at", "TIMESTAMP WITH TIME ZONE"),
)
RISK_BEFORE_CLOCK = "risk-before-clock"
CLOCK_BEFORE_RISK = "clock-before-risk"
LAYOUTS = {RISK_BEFORE_CLOCK: SCHEMA, CLOCK_BEFORE_RISK: (*SCHEMA[:9], SCHEMA[10], SCHEMA[9])}
MAX_ROWS = 1000
MAX_CELL = 65536
MAX_BYTES = 1048576
MAX_RECORD = 524288
MAX_RECORDS = 4194304
DEFINITION = (
    VERSION,
    PROJECTION_VERSION,
    SCHEMA,
    LAYOUTS,
    MAX_ROWS,
    MAX_CELL,
    MAX_BYTES,
    MAX_RECORD,
    MAX_RECORDS,
    "explicit exact physical layout; named-field canonical rows",
    "no positional repair, recovered history, native policy permission or time authority",
)
Rejected = primitives.Rejected
canonical = primitives.canonical
sha = primitives.sha
pin = primitives.pin
label = primitives.label
parse = primitives.parse


def checked_layout(layout_id: str) -> tuple[tuple[str, str], ...]:
    if type(layout_id) is not str or layout_id not in LAYOUTS:
        raise Rejected("EXPLICIT_REVIEWED_POLICY_LAYOUT_REQUIRED")
    return LAYOUTS[layout_id]


@dataclass(frozen=True)
class Snapshot:
    snapshot_id: str
    payload: bytes
    row_count: int


def encode_cell(value: object, kind: str) -> object:
    if value is None:
        return None
    if kind == "DATE":
        if type(value) is not date:
            raise Rejected("EXACT_STORED_POLICY_DATE_REQUIRED")
        return value.isoformat()
    if kind == "TIMESTAMP WITH TIME ZONE":
        return common._clock(value)
    if kind not in ("VARCHAR", "JSON") or type(value) is not str or len(value.encode()) > MAX_CELL:
        raise Rejected("EXACT_BOUNDED_POLICY_TEXT_REQUIRED")
    return value


def _row(row: object) -> list[Any]:
    if type(row) is not list or len(row) != len(SCHEMA):
        raise Rejected("EXACT_POLICY_ROW_REQUIRED")
    if type(row[0]) is not str:
        raise Rejected("NON_NULL_STORED_POLICY_KEY_REQUIRED")
    for value, (_name, kind) in zip(row, SCHEMA, strict=True):
        if value is None:
            continue
        if type(value) is not str:
            raise Rejected("EXACT_ENCODED_POLICY_CELL_REQUIRED")
        original = value
        if kind == "DATE":
            if len(value) > 10:
                raise Rejected("DATE_TEXT_BOUND")
            value = date.fromisoformat(value)
        elif kind == "TIMESTAMP WITH TIME ZONE":
            if len(value) > 64:
                raise Rejected("CLOCK_TEXT_BOUND")
            value = datetime.fromisoformat(value)
        if encode_cell(value, kind) != original:
            raise Rejected("NONCANONICAL_STORED_POLICY_CELL")
    return row


def make_snapshot(source_label: str, rows: list[list[Any]], *, layout_id: str) -> Snapshot:
    physical = checked_layout(layout_id)
    if not label(source_label):
        raise Rejected("EXPLICIT_SOURCE_LABEL_REQUIRED")
    if type(rows) is not list or not 1 <= len(rows) <= MAX_ROWS:
        raise Rejected("WHOLE_TABLE_ROW_BOUND")
    try:
        checked = [_row(r) for r in rows]
        if len({r[0] for r in checked}) != len(checked):
            raise Rejected("DUPLICATE_STORED_POLICY_KEY")
        raw = canonical(
            dict(
                version=VERSION,
                table=TABLE,
                columns=SCHEMA,
                physical_columns=physical,
                layout_id=layout_id,
                source_label=source_label,
                rows=sorted(checked, key=lambda r: canonical(r[0])),
            )
        )
        if len(raw) > MAX_BYTES:
            raise Rejected("SNAPSHOT_BYTE_BOUND")
        return Snapshot(sha(raw), raw, len(rows))
    except Rejected:
        raise
    except (ValueError, TypeError, UnicodeError, OverflowError):
        raise Rejected("MALFORMED_STORED_POLICY_ROW") from None


def replay_snapshot(raw: bytes, *, expected_snapshot_id: str) -> dict[str, Any]:
    doc = parse(raw, MAX_BYTES)
    if not pin(expected_snapshot_id) or sha(raw) != expected_snapshot_id:
        raise Rejected("EXACT_SNAPSHOT_PIN_REQUIRED")
    try:
        rebuilt = make_snapshot(doc["source_label"], doc["rows"], layout_id=doc["layout_id"])
        if rebuilt.payload != raw:
            raise Rejected("COMPLETE_POLICY_REPLAY_MISMATCH")
        return doc
    except Rejected:
        raise
    except (ValueError, TypeError, KeyError, RecursionError):
        raise Rejected("POLICY_SNAPSHOT_SCHEMA") from None


def derive_records(
    raw: bytes, *, snapshot_id: str, capture_event_id: str, envelope_hash: str
) -> tuple[bytes, ...]:
    if not all(pin(p) for p in (snapshot_id, capture_event_id, envelope_hash)):
        raise Rejected("EXACT_BRONZE_PINS_REQUIRED")
    doc = replay_snapshot(raw, expected_snapshot_id=snapshot_id)
    records = []
    for ordinal, row in enumerate(doc["rows"]):
        fields = dict(zip((n for n, _ in SCHEMA), row, strict=True))
        flags = []
        for name in ("policy_id", "symbol", "selection_status"):
            if fields[name] is None:
                flags.append("MISSING_STORED_" + name.upper())
            elif not fields[name].strip():
                flags.append("EMPTY_OR_WHITESPACE_" + name.upper())
        for start, end in (("train_start", "train_end"), ("test_start", "test_end")):
            if (
                fields[start] is not None
                and fields[end] is not None
                and fields[start] > fields[end]
            ):
                flags.append("REVERSED_STORED_" + start.split("_")[0].upper() + "_DATES")
        record = canonical(
            dict(
                version=PROJECTION_VERSION,
                source_snapshot_id=snapshot_id,
                source_capture_event_id=capture_event_id,
                source_envelope_hash=envelope_hash,
                source_layout_id=doc["layout_id"],
                source_ordinal=ordinal,
                source_table=TABLE,
                stored_fields=fields,
                flags=flags,
                classification="RETAINED_LEGACY_POLICY_OUTPUT_NOT_AUTHORIZED",
                source_revision_history_complete=False,
                original_provider_bytes_retained=False,
                policy_json_interpreted=False,
                native_policy_recomputed=False,
                policy_authorized=False,
                training_causality_verified=False,
                canonical_identity=None,
                original_availability_at=None,
                economic_validity_at=None,
                publication_asserted=False,
                decision_eligibility_asserted=False,
            )
        )
        if len(record) > MAX_RECORD:
            raise Rejected("POLICY_RECORD_BYTE_BOUND")
        records.append(record)
    if sum(map(len, records)) > MAX_RECORDS:
        raise Rejected("POLICY_AGGREGATE_BYTE_BOUND")
    return tuple(records)
