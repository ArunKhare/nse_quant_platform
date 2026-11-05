"""Exact retained feature snapshots; diagnostics are opaque retained JSON text."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from nse_quant.data_platform import legacy_daily_rv as primitives
from nse_quant.data_platform import legacy_daily_rv_bronze as common

VERSION = "legacy-feature-snapshot@1"
PROJECTION_VERSION = "legacy-feature-observation@1"
TABLE = "feature_snapshots"
SCHEMA = (
    ("feature_id", "VARCHAR"),
    ("ts", "TIMESTAMP WITH TIME ZONE"),
    ("run_id", "VARCHAR"),
    ("underlying", "VARCHAR"),
    ("expiry", "DATE"),
    ("spot", "DOUBLE"),
    ("atm_iv", "DOUBLE"),
    ("iv_rank", "DOUBLE"),
    ("iv_percentile", "DOUBLE"),
    ("realized_vol", "DOUBLE"),
    ("iv_rv_spread", "DOUBLE"),
    ("pcr", "DOUBLE"),
    ("total_call_oi", "BIGINT"),
    ("total_put_oi", "BIGINT"),
    ("max_pain", "DOUBLE"),
    ("liquidity_score", "DOUBLE"),
    ("regime", "VARCHAR"),
    ("short_momentum", "DOUBLE"),
    ("straddle_price", "DOUBLE"),
    ("expected_move_pct", "DOUBLE"),
    ("expected_move_points", "DOUBLE"),
    ("diagnostics", "JSON"),
)
MAX_ROWS = 1000
MAX_CELL = 65536
MAX_BYTES = 1048576
MAX_RECORD = 524288
MAX_RECORDS = 4194304
DEFINITION = (
    VERSION,
    PROJECTION_VERSION,
    SCHEMA,
    MAX_ROWS,
    MAX_CELL,
    MAX_BYTES,
    MAX_RECORD,
    MAX_RECORDS,
    "feature_id is opaque; run_id is not a revision key",
    "diagnostics are stored text, never interpreted authorization",
    "all retained analytics remain legacy derived; no recomputation/history claim",
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


def encode_cell(value: object, kind: str) -> object:
    if value is None:
        return None
    if kind == "DOUBLE":
        if type(value) is not float or not math.isfinite(value):
            raise Rejected("FINITE_BINARY64_REQUIRED")
        return value.hex()
    if kind == "BIGINT":
        if type(value) is not int or not -(2**63) <= value < 2**63:
            raise Rejected("EXACT_BIGINT_REQUIRED")
        return str(value)
    if kind == "DATE":
        if type(value) is not date:
            raise Rejected("EXACT_STORED_DATE_REQUIRED")
        return value.isoformat()
    if kind == "TIMESTAMP WITH TIME ZONE":
        return common._clock(value)
    if type(value) is not str or len(value.encode()) > MAX_CELL:
        raise Rejected("TEXT_CELL_BOUND")
    return value


def _row(row: object) -> list[Any]:
    if type(row) is not list or len(row) != len(SCHEMA):
        raise Rejected("EXACT_FEATURE_ROW_REQUIRED")
    if type(row[0]) is not str:
        raise Rejected("NON_NULL_STORED_FEATURE_KEY_REQUIRED")
    for value, (_name, kind) in zip(row, SCHEMA, strict=True):
        if value is None:
            continue
        if type(value) is not str:
            raise Rejected("EXACT_ENCODED_FEATURE_CELL_REQUIRED")
        original = value
        if kind == "DOUBLE":
            if len(value) > 64:
                raise Rejected("BINARY64_TEXT_BOUND")
            value = float.fromhex(value)
        elif kind == "BIGINT":
            if len(value) > 20:
                raise Rejected("BIGINT_TEXT_BOUND")
            value = int(value)
        elif kind == "DATE":
            if len(value) > 10:
                raise Rejected("DATE_TEXT_BOUND")
            value = date.fromisoformat(value)
        elif kind == "TIMESTAMP WITH TIME ZONE":
            if len(value) > 64:
                raise Rejected("CLOCK_TEXT_BOUND")
            value = datetime.fromisoformat(value)
        if encode_cell(value, kind) != original:
            raise Rejected("NONCANONICAL_STORED_FEATURE_CELL")
    return row


def make_snapshot(source_label: str, rows: list[list[Any]]) -> Snapshot:
    if not label(source_label):
        raise Rejected("EXPLICIT_SOURCE_LABEL_REQUIRED")
    if type(rows) is not list or not 1 <= len(rows) <= MAX_ROWS:
        raise Rejected("WHOLE_TABLE_ROW_BOUND")
    try:
        checked = [_row(r) for r in rows]
        if len({r[0] for r in checked}) != len(checked):
            raise Rejected("DUPLICATE_STORED_FEATURE_KEY")
        raw = canonical(
            dict(
                version=VERSION,
                table=TABLE,
                columns=SCHEMA,
                source_label=source_label,
                rows=sorted(checked, key=lambda r: canonical(r[0])),
            )
        )
        if len(raw) > MAX_BYTES:
            raise Rejected("SNAPSHOT_BYTE_BOUND")
        return Snapshot(sha(raw), raw, len(rows))
    except Rejected:
        raise
    except (ValueError, TypeError, OverflowError, UnicodeError):
        raise Rejected("MALFORMED_STORED_FEATURE_ROW") from None


def replay_snapshot(raw: bytes, *, expected_snapshot_id: str) -> dict[str, Any]:
    doc = parse(raw, MAX_BYTES)
    if not pin(expected_snapshot_id) or sha(raw) != expected_snapshot_id:
        raise Rejected("EXACT_SNAPSHOT_PIN_REQUIRED")
    try:
        if make_snapshot(doc["source_label"], doc["rows"]).payload != raw:
            raise Rejected("COMPLETE_FEATURE_SNAPSHOT_REPLAY_MISMATCH")
        return doc
    except Rejected:
        raise
    except (ValueError, TypeError, KeyError, RecursionError):
        raise Rejected("FEATURE_SNAPSHOT_SCHEMA") from None


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
        for name in ("feature_id", "run_id", "underlying", "regime"):
            if fields[name] is None:
                flags.append("MISSING_" + name.upper())
            elif not fields[name].strip():
                flags.append("EMPTY_OR_WHITESPACE_" + name.upper())
        for name in ("ts", "expiry"):
            if fields[name] is None:
                flags.append("MISSING_" + name.upper())
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
                classification="RETAINED_LEGACY_FEATURES_NOT_RECOMPUTED",
                source_revision_history_complete=False,
                original_provider_bytes_retained=False,
                diagnostics_interpreted=False,
                native_features_recomputed=False,
                canonical_identity=None,
                original_availability_at=None,
                economic_validity_at=None,
                publication_asserted=False,
                decision_eligibility_asserted=False,
            )
        )
        if len(record) > MAX_RECORD:
            raise Rejected("FEATURE_RECORD_BYTE_BOUND")
        records.append(record)
    if sum(map(len, records)) > MAX_RECORDS:
        raise Rejected("FEATURE_AGGREGATE_BYTE_BOUND")
    return tuple(records)
