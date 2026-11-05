"""Exact retained spot-feature evidence, never recovered candles or recomputed Gold."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from nse_quant.data_platform import legacy_daily_rv as primitives
from nse_quant.data_platform import legacy_daily_rv_bronze as common

VERSION = "legacy-spot-feature-snapshot@1"
PROJECTION_VERSION = "legacy-spot-feature-observation@1"
TABLE = "spot_features"
NAMES = (
    "symbol",
    "ts",
    "close",
    "return_1m",
    "rv_1m_30",
    "atr_1m_14",
    "vwap_1m",
    "vwap_distance_1m",
    "volume_zscore_1m_30",
    "trend_15m",
    "atr_15m_14",
    "range_position_15m",
    "trend_60m",
    "atr_60m_14",
    "range_position_60m",
)
SCHEMA = tuple(zip(NAMES, ("VARCHAR", "TIMESTAMP WITH TIME ZONE", *("DOUBLE",) * 13), strict=True))
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
    "entire retained table; stored symbol/instant key",
    "legacy-derived values; names are not authenticated analytical definitions",
    "no recovered overwritten history/provider bytes/availability/coverage",
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
            raise Rejected("FINITE_STORED_BINARY64_REQUIRED")
        return value.hex()
    if kind == "TIMESTAMP WITH TIME ZONE":
        return common._clock(value)
    if kind != "VARCHAR" or type(value) is not str or len(value.encode()) > MAX_CELL:
        raise Rejected("EXACT_BOUNDED_SYMBOL_REQUIRED")
    return value


def _row(row: object) -> list[Any]:
    if type(row) is not list or len(row) != len(SCHEMA):
        raise Rejected("EXACT_SPOT_FEATURE_ROW_REQUIRED")
    if any(type(row[i]) is not str for i in (0, 1)):
        raise Rejected("NON_NULL_STORED_SPOT_KEY_REQUIRED")
    for value, (_name, kind) in zip(row, SCHEMA, strict=True):
        if value is None:
            continue
        if type(value) is not str:
            raise Rejected("EXACT_ENCODED_SPOT_CELL_REQUIRED")
        original = value
        if kind == "DOUBLE":
            if len(value) > 64:
                raise Rejected("BINARY64_TEXT_BOUND")
            value = float.fromhex(value)
        elif kind == "TIMESTAMP WITH TIME ZONE":
            if len(value) > 64:
                raise Rejected("CLOCK_TEXT_BOUND")
            value = datetime.fromisoformat(value)
        if encode_cell(value, kind) != original:
            raise Rejected("NONCANONICAL_STORED_SPOT_CELL")
    return row


def make_snapshot(source_label: str, rows: list[list[Any]]) -> Snapshot:
    """Pure encoded evidence construction, not SQL source attestation."""
    if not label(source_label):
        raise Rejected("EXPLICIT_SOURCE_LABEL_REQUIRED")
    if type(rows) is not list or not 1 <= len(rows) <= MAX_ROWS:
        raise Rejected("WHOLE_TABLE_ROW_BOUND")
    try:
        checked = [_row(row) for row in rows]
        keys = [canonical(row[:2]) for row in checked]
        if len(set(keys)) != len(keys):
            raise Rejected("DUPLICATE_STORED_SPOT_KEY")
        raw = canonical(
            dict(
                version=VERSION,
                table=TABLE,
                columns=SCHEMA,
                source_label=source_label,
                rows=sorted(checked, key=lambda row: canonical(row[:2])),
            )
        )
        if len(raw) > MAX_BYTES:
            raise Rejected("SNAPSHOT_BYTE_BOUND")
        return Snapshot(sha(raw), raw, len(rows))
    except Rejected:
        raise
    except (ValueError, TypeError, UnicodeError, OverflowError):
        raise Rejected("MALFORMED_STORED_SPOT_FEATURE_ROW") from None


def replay_snapshot(raw: bytes, *, expected_snapshot_id: str) -> dict[str, Any]:
    doc = parse(raw, MAX_BYTES)
    if not pin(expected_snapshot_id) or sha(raw) != expected_snapshot_id:
        raise Rejected("EXACT_SNAPSHOT_PIN_REQUIRED")
    try:
        if make_snapshot(doc["source_label"], doc["rows"]).payload != raw:
            raise Rejected("COMPLETE_SPOT_FEATURE_REPLAY_MISMATCH")
        return doc
    except Rejected:
        raise
    except (ValueError, TypeError, KeyError, RecursionError):
        raise Rejected("SPOT_FEATURE_SNAPSHOT_SCHEMA") from None


def derive_records(
    raw: bytes, *, snapshot_id: str, capture_event_id: str, envelope_hash: str
) -> tuple[bytes, ...]:
    if not all(pin(p) for p in (snapshot_id, capture_event_id, envelope_hash)):
        raise Rejected("EXACT_BRONZE_PINS_REQUIRED")
    doc = replay_snapshot(raw, expected_snapshot_id=snapshot_id)
    records = []
    for ordinal, row in enumerate(doc["rows"]):
        fields = dict(zip(NAMES, row, strict=True))
        flags = []
        if not fields["symbol"].strip():
            flags.append("EMPTY_OR_WHITESPACE_STORED_SYMBOL")
        for name in NAMES[2:]:
            if fields[name] is None:
                flags.append("MISSING_STORED_" + name.upper())
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
                classification="RETAINED_LEGACY_SPOT_FEATURES_NOT_RECOMPUTED",
                source_revision_history_complete=False,
                original_provider_bytes_retained=False,
                native_features_recomputed=False,
                analytical_assumptions_verified=False,
                authoritative_market_coverage_verified=False,
                canonical_identity=None,
                original_availability_at=None,
                economic_validity_at=None,
                publication_asserted=False,
                decision_eligibility_asserted=False,
            )
        )
        if len(record) > MAX_RECORD:
            raise Rejected("SPOT_FEATURE_RECORD_BYTE_BOUND")
        records.append(record)
    if sum(map(len, records)) > MAX_RECORDS:
        raise Rejected("SPOT_FEATURE_AGGREGATE_BYTE_BOUND")
    return tuple(records)
