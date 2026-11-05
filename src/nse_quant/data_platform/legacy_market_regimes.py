"""Exact retained regime labels and opaque features JSON, never native policy authority."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from nse_quant.data_platform import legacy_daily_rv as primitives
from nse_quant.data_platform import legacy_daily_rv_bronze as common

VERSION = "legacy-market-regime-snapshot@1"
PROJECTION_VERSION = "legacy-market-regime-observation@1"
TABLE = "market_regimes"
SCHEMA = (
    ("symbol", "VARCHAR"),
    ("ts", "TIMESTAMP WITH TIME ZONE"),
    ("trend_regime", "VARCHAR"),
    ("volatility_regime", "VARCHAR"),
    ("iv_regime", "VARCHAR"),
    ("regime", "VARCHAR"),
    ("features", "JSON"),
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
    "key=symbol+stored UTC instant; no overwritten history",
    "labels and exact stored JSON are legacy output, not native regime/policy authority",
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
    if kind == "TIMESTAMP WITH TIME ZONE":
        return common._clock(value)
    if kind not in ("VARCHAR", "JSON") or type(value) is not str or len(value.encode()) > MAX_CELL:
        raise Rejected("EXACT_BOUNDED_REGIME_TEXT_REQUIRED")
    return value


def _row(row: object) -> list[Any]:
    if type(row) is not list or len(row) != len(SCHEMA):
        raise Rejected("EXACT_REGIME_ROW_REQUIRED")
    if any(type(row[i]) is not str for i in (0, 1)):
        raise Rejected("NON_NULL_REGIME_KEY_REQUIRED")
    for value, (_name, kind) in zip(row, SCHEMA, strict=True):
        if value is None:
            continue
        if type(value) is not str:
            raise Rejected("EXACT_ENCODED_REGIME_CELL_REQUIRED")
        original = value
        if kind == "TIMESTAMP WITH TIME ZONE":
            if len(value) > 64:
                raise Rejected("CLOCK_TEXT_BOUND")
            value = datetime.fromisoformat(value)
        if encode_cell(value, kind) != original:
            raise Rejected("NONCANONICAL_STORED_REGIME_CELL")
    return row


def make_snapshot(source_label: str, rows: list[list[Any]]) -> Snapshot:
    """Pure content construction, never original SQL capture attestation."""
    if not label(source_label):
        raise Rejected("EXPLICIT_SOURCE_LABEL_REQUIRED")
    if type(rows) is not list or not 1 <= len(rows) <= MAX_ROWS:
        raise Rejected("WHOLE_TABLE_ROW_BOUND")
    try:
        checked = [_row(r) for r in rows]
        if len({canonical(r[:2]) for r in checked}) != len(checked):
            raise Rejected("DUPLICATE_STORED_REGIME_KEY")
        raw = canonical(
            dict(
                version=VERSION,
                table=TABLE,
                columns=SCHEMA,
                source_label=source_label,
                rows=sorted(checked, key=lambda r: canonical(r[:2])),
            )
        )
        if len(raw) > MAX_BYTES:
            raise Rejected("SNAPSHOT_BYTE_BOUND")
        return Snapshot(sha(raw), raw, len(rows))
    except Rejected:
        raise
    except (ValueError, TypeError, UnicodeError, OverflowError):
        raise Rejected("MALFORMED_STORED_REGIME_ROW") from None


def replay_snapshot(raw: bytes, *, expected_snapshot_id: str) -> dict[str, Any]:
    doc = parse(raw, MAX_BYTES)
    if not pin(expected_snapshot_id) or sha(raw) != expected_snapshot_id:
        raise Rejected("EXACT_SNAPSHOT_PIN_REQUIRED")
    try:
        if make_snapshot(doc["source_label"], doc["rows"]).payload != raw:
            raise Rejected("COMPLETE_REGIME_REPLAY_MISMATCH")
        return doc
    except Rejected:
        raise
    except (ValueError, TypeError, KeyError, RecursionError):
        raise Rejected("REGIME_SNAPSHOT_SCHEMA") from None


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
        for name in ("symbol", "trend_regime", "volatility_regime", "iv_regime", "regime"):
            if fields[name] is None:
                flags.append("MISSING_STORED_" + name.upper())
            elif not fields[name].strip():
                flags.append("EMPTY_OR_WHITESPACE_" + name.upper())
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
                classification="RETAINED_LEGACY_REGIME_OUTPUT_NOT_RECOMPUTED",
                source_revision_history_complete=False,
                original_provider_bytes_retained=False,
                features_interpreted=False,
                native_regime_recomputed=False,
                policy_authorized=False,
                canonical_identity=None,
                original_availability_at=None,
                economic_validity_at=None,
                publication_asserted=False,
                decision_eligibility_asserted=False,
            )
        )
        if len(record) > MAX_RECORD:
            raise Rejected("REGIME_RECORD_BYTE_BOUND")
        records.append(record)
    if sum(map(len, records)) > MAX_RECORDS:
        raise Rejected("REGIME_AGGREGATE_BYTE_BOUND")
    return tuple(records)
