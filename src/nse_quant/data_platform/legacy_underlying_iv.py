"""Exact retained underlying-IV SQL evidence, never native solver output."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from nse_quant.data_platform import legacy_daily_rv as primitives
from nse_quant.data_platform import legacy_daily_rv_bronze as common

VERSION = "legacy-underlying-iv-snapshot@1"
SILVER_VERSION = "legacy-underlying-iv-silver@1"
TABLE = "underlying_iv_observations"
SCHEMA = (
    ("ts", "TIMESTAMP WITH TIME ZONE"),
    ("underlying", "VARCHAR"),
    ("expiry", "DATE"),
    ("iv", "DOUBLE"),
    ("spot", "DOUBLE"),
    ("source", "VARCHAR"),
)
MAX_ROWS = 1000
MAX_CELL = 65536
MAX_BYTES = 1048576
MAX_RECORD = 150000
MAX_RECORDS = 4194304
MAX_CONTEXT = 2200000
DEFINITION = (
    VERSION,
    SILVER_VERSION,
    SCHEMA,
    MAX_ROWS,
    MAX_CELL,
    MAX_BYTES,
    MAX_RECORD,
    MAX_RECORDS,
    MAX_CONTEXT,
    "stored source is a label; stored timestamp is not availability",
    "legacy-derived IV; no original bytes/history/native solver/identity claim",
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


def _float(value: object) -> None:
    if type(value) is not str:
        raise Rejected("EXACT_FINITE_BINARY64_REQUIRED")
    number = float.fromhex(value)
    if not math.isfinite(number) or number.hex() != value:
        raise Rejected("EXACT_FINITE_BINARY64_REQUIRED")


def _row(row: object) -> list[Any]:
    if type(row) is not list or len(row) != 6:
        raise Rejected("EXACT_IV_ROW_REQUIRED")
    ts, underlying, expiry, iv, spot, stored_source = row
    if any(type(v) is not str for v in (ts, underlying, expiry, iv, stored_source)):
        raise Rejected("EXACT_NON_NULL_IV_FIELDS_REQUIRED")
    if any(len(v.encode()) > MAX_CELL for v in (underlying, stored_source)):
        raise Rejected("TEXT_CELL_BOUND")
    if len(ts) > 64 or common._clock(datetime.fromisoformat(ts)) != ts:
        raise Rejected("CANONICAL_AWARE_STORED_TS_REQUIRED")
    if len(expiry) > 10 or date.fromisoformat(expiry).isoformat() != expiry:
        raise Rejected("CANONICAL_STORED_DATE_REQUIRED")
    if len(iv) > 64 or (spot is not None and (type(spot) is not str or len(spot) > 64)):
        raise Rejected("BINARY64_TEXT_BOUND")
    _float(iv)
    if spot is not None:
        _float(spot)
    return row


def make_snapshot(source_label: str, rows: list[list[Any]]) -> Snapshot:
    """Pure encoded constructor is not a source attestation."""
    if not label(source_label):
        raise Rejected("EXPLICIT_SOURCE_LABEL_REQUIRED")
    if type(rows) is not list or not 1 <= len(rows) <= MAX_ROWS:
        raise Rejected("WHOLE_TABLE_ROW_BOUND")
    try:
        checked = [_row(r) for r in rows]
        keys = [canonical(r[:3]) for r in checked]
        if len(set(keys)) != len(keys):
            raise Rejected("DUPLICATE_STORED_KEY")
        raw = canonical(
            dict(
                version=VERSION,
                table=TABLE,
                columns=SCHEMA,
                source_label=source_label,
                rows=sorted(checked, key=lambda r: canonical(r[:3])),
            )
        )
        if len(raw) > MAX_BYTES:
            raise Rejected("SNAPSHOT_BYTE_BOUND")
        return Snapshot(sha(raw), raw, len(rows))
    except Rejected:
        raise
    except (ValueError, TypeError, OverflowError, UnicodeError):
        raise Rejected("MALFORMED_STORED_IV_ROW") from None


def replay_snapshot(raw: bytes, *, expected_snapshot_id: str) -> dict[str, Any]:
    doc = parse(raw, MAX_BYTES)
    if not pin(expected_snapshot_id) or sha(raw) != expected_snapshot_id:
        raise Rejected("EXACT_SNAPSHOT_PIN_REQUIRED")
    try:
        if make_snapshot(doc["source_label"], doc["rows"]).payload != raw:
            raise Rejected("COMPLETE_IV_SNAPSHOT_REPLAY_MISMATCH")
        return doc
    except Rejected:
        raise
    except (ValueError, TypeError, KeyError, RecursionError):
        raise Rejected("IV_SNAPSHOT_SCHEMA") from None


def derive_records(
    raw: bytes, *, snapshot_id: str, capture_event_id: str, envelope_hash: str
) -> tuple[bytes, ...]:
    if not all(pin(p) for p in (snapshot_id, capture_event_id, envelope_hash)):
        raise Rejected("EXACT_BRONZE_PINS_REQUIRED")
    doc = replay_snapshot(raw, expected_snapshot_id=snapshot_id)
    records = []
    for ordinal, row in enumerate(doc["rows"]):
        _ts, underlying, _expiry, iv, spot, stored_source = row
        flags = []
        if not underlying.strip():
            flags.append("EMPTY_OR_WHITESPACE_UNDERLYING")
        if not stored_source.strip():
            flags.append("EMPTY_OR_WHITESPACE_SOURCE_LABEL")
        if float.fromhex(iv) <= 0:
            flags.append("NONPOSITIVE_LEGACY_IV")
        if spot is None:
            flags.append("MISSING_STORED_SPOT")
        elif float.fromhex(spot) <= 0:
            flags.append("NONPOSITIVE_STORED_SPOT")
        raw_record = canonical(
            dict(
                version=SILVER_VERSION,
                source_snapshot_id=snapshot_id,
                source_capture_event_id=capture_event_id,
                source_envelope_hash=envelope_hash,
                source_ordinal=ordinal,
                source_table=TABLE,
                stored_fields=dict(zip((c[0] for c in SCHEMA), row, strict=True)),
                flags=flags,
                classification="RETAINED_LEGACY_DERIVED_IV_NOT_RECOMPUTED",
                stored_ts_semantics="LEGACY_STORED_INSTANT_NOT_INDEPENDENT_AVAILABILITY",
                stored_expiry_semantics="LEGACY_DATE_NOT_VERIFIED_SETTLEMENT",
                stored_source_semantics="LEGACY_LABEL_NOT_AUTHENTICATED_PROVIDER",
                source_revision_history_complete=False,
                original_provider_bytes_retained=False,
                native_iv_recomputed=False,
                solver_assumptions_verified=False,
                canonical_identity=None,
                original_availability_at=None,
                economic_validity_at=None,
                publication_asserted=False,
                decision_eligibility_asserted=False,
            )
        )
        if len(raw_record) > MAX_RECORD:
            raise Rejected("SILVER_RECORD_BYTE_BOUND")
        records.append(raw_record)
    if sum(map(len, records)) > MAX_RECORDS:
        raise Rejected("SILVER_AGGREGATE_BYTE_BOUND")
    return tuple(records)
