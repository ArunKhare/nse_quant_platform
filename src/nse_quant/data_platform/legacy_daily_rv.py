"""Exact retained daily RV evidence; not native RV recomputation or decision admission."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import date
from typing import Any

VERSION = "legacy-daily-rv-snapshot@1"
SILVER_VERSION = "legacy-daily-rv-silver@1"
TABLE = "daily_rv_observations"
SCHEMA = (
    ("symbol", "VARCHAR"),
    ("trading_date", "DATE"),
    ("rv", "DOUBLE"),
    ("observation_count", "BIGINT"),
)
MAX_ROWS = 1000
MAX_CELL = 65536
MAX_BYTES = 1048576
MAX_RECORD = 70000
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
    "retained whole table, no overwritten history, no original receipt clock",
    "DATE is a stored label, not session/availability/economic validity",
    "rv is legacy-derived finite binary64, not recomputed or annualization-validated",
)


class Rejected(ValueError):
    """Fixed diagnostics. Operational errors propagate."""


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
            raise Rejected("DUPLICATE_JSON_KEY")
        result[k] = v
    return result


def _invalid(value: str) -> Any:
    raise Rejected("NONFINITE_JSON")


def parse(raw: bytes, maximum: int) -> dict[str, Any]:
    if type(raw) is not bytes or not 0 < len(raw) <= maximum:
        raise Rejected("BYTE_BOUND")
    try:
        doc = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_invalid)
        if type(doc) is not dict or canonical(doc) != raw:
            raise Rejected("CANONICAL_OBJECT_REQUIRED")
        return doc
    except Rejected:
        raise
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        raise Rejected("MALFORMED_JSON") from None


@dataclass(frozen=True)
class Snapshot:
    snapshot_id: str
    payload: bytes
    row_count: int


def _row(row: object) -> list[str]:
    if type(row) is not list or len(row) != 4 or any(type(v) is not str for v in row):
        raise Rejected("EXACT_NON_NULL_ROW_REQUIRED")
    symbol, day, rv, count = row
    if len(symbol.encode()) > MAX_CELL:
        raise Rejected("TEXT_CELL_BOUND")
    if date.fromisoformat(day).isoformat() != day:
        raise Rejected("CANONICAL_DATE_REQUIRED")
    value = float.fromhex(rv)
    if not math.isfinite(value) or value.hex() != rv:
        raise Rejected("FINITE_BINARY64_HEX_REQUIRED")
    number = int(count)
    if str(number) != count or not -(2**63) <= number < 2**63:
        raise Rejected("CANONICAL_BIGINT_REQUIRED")
    return row


def make_snapshot(source_label: str, rows: list[list[str]]) -> Snapshot:
    """Pure encoded evidence constructor, not SQL source attestation."""
    if not label(source_label):
        raise Rejected("EXPLICIT_SOURCE_LABEL_REQUIRED")
    if type(rows) is not list or not 1 <= len(rows) <= MAX_ROWS:
        raise Rejected("WHOLE_TABLE_ROW_BOUND")
    try:
        checked = [_row(r) for r in rows]
        keys = [canonical(r[:2]) for r in checked]
        if len(set(keys)) != len(keys):
            raise Rejected("DUPLICATE_STORED_KEY")
        ordered = sorted(checked, key=lambda r: canonical(r[:2]))
        raw = canonical(
            dict(
                version=VERSION,
                table=TABLE,
                columns=SCHEMA,
                source_label=source_label,
                rows=ordered,
            )
        )
        if len(raw) > MAX_BYTES:
            raise Rejected("SNAPSHOT_BYTE_BOUND")
        return Snapshot(sha(raw), raw, len(rows))
    except Rejected:
        raise
    except (ValueError, TypeError, UnicodeError, OverflowError):
        raise Rejected("MALFORMED_STORED_ROW") from None


def replay_snapshot(raw: bytes, *, expected_snapshot_id: str) -> dict[str, Any]:
    if not pin(expected_snapshot_id) or sha(raw) != expected_snapshot_id:
        raise Rejected("EXACT_SNAPSHOT_PIN_REQUIRED")
    doc = parse(raw, MAX_BYTES)
    try:
        rebuilt = make_snapshot(doc["source_label"], doc["rows"])
        if rebuilt.payload != raw:
            raise Rejected("COMPLETE_SNAPSHOT_REPLAY_MISMATCH")
        return doc
    except Rejected:
        raise
    except (KeyError, ValueError, TypeError):
        raise Rejected("SNAPSHOT_SCHEMA") from None


def derive_records(
    raw: bytes, *, snapshot_id: str, capture_event_id: str, envelope_hash: str
) -> tuple[bytes, ...]:
    """Full deterministic source-linked projection. Does not authenticate native storage."""
    if not all(pin(p) for p in (snapshot_id, capture_event_id, envelope_hash)):
        raise Rejected("EXACT_BRONZE_PINS_REQUIRED")
    doc = replay_snapshot(raw, expected_snapshot_id=snapshot_id)
    records = []
    for ordinal, row in enumerate(doc["rows"]):
        symbol, day, rv, count = row
        flags = []
        if not symbol.strip():
            flags.append("EMPTY_OR_WHITESPACE_SYMBOL")
        if float.fromhex(rv) < 0:
            flags.append("NEGATIVE_LEGACY_RV")
        if float.fromhex(rv) == 0:
            flags.append("ZERO_LEGACY_RV")
        if int(count) <= 0:
            flags.append("NONPOSITIVE_OBSERVATION_COUNT")
        record = canonical(
            dict(
                version=SILVER_VERSION,
                source_snapshot_id=snapshot_id,
                source_capture_event_id=capture_event_id,
                source_envelope_hash=envelope_hash,
                source_ordinal=ordinal,
                source_table=TABLE,
                stored_fields=dict(zip((c[0] for c in SCHEMA), row, strict=True)),
                classification="RETAINED_LEGACY_DERIVED_RV_NOT_RECOMPUTED",
                flags=flags,
                stored_date_semantics="LEGACY_DATE_LABEL_NOT_VERIFIED_SESSION",
                source_revision_history_complete=False,
                original_provider_bytes_retained=False,
                original_availability_at=None,
                economic_validity_at=None,
                canonical_identity=None,
                authoritative_market_coverage_verified=False,
                annualization_verified=False,
                native_rv_recomputed=False,
                publication_asserted=False,
                decision_eligibility_asserted=False,
            )
        )
        if len(record) > MAX_RECORD:
            raise Rejected("SILVER_RECORD_BYTE_BOUND")
        records.append(record)
    if sum(map(len, records)) > MAX_RECORDS:
        raise Rejected("SILVER_AGGREGATE_BYTE_BOUND")
    return tuple(records)
