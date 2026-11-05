"""Bounded retained market-regime content; never native regime truth or admission."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

VERSION = "legacy-market-regimes-snapshot@1"
OBSERVATION_VERSION = "legacy-market-regime-observation@1"
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
KEY = ("symbol", "ts")
MAX_ROWS = 1000
MAX_CELL = 65536
MAX_BYTES = 1048576
MAX_RECORD = 524288
MAX_RECORDS = 4194304
DEFINITION = (
    VERSION,
    OBSERVATION_VERSION,
    SCHEMA,
    KEY,
    MAX_ROWS,
    MAX_CELL,
    MAX_BYTES,
    MAX_RECORD,
    MAX_RECORDS,
    "whole retained base table; composite key only; all non-key fields nullable",
    "stored TIMESTAMPTZ instant or unknown; no regime truth",
    "opaque JSON CAST(JSON AS VARCHAR); SQL NULL distinct from JSON null",
    "no recovered overwritten history, regime interpretation, execution replay or admission",
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


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise Rejected("DUPLICATE_MARKET_REGIME_OUTER_JSON_KEY")
        result[key] = value
    return result


def _invalid(_value: str) -> Any:
    raise Rejected("NONFINITE_MARKET_REGIME_OUTER_JSON")


def parse(raw: bytes, maximum: int) -> dict[str, Any]:
    if type(raw) is not bytes or not 0 < len(raw) <= maximum:
        raise Rejected("MARKET_REGIME_CONTENT_BYTE_BOUND")
    try:
        value = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_invalid)
        if type(value) is not dict or canonical(value) != raw:
            raise Rejected("EXACT_CANONICAL_MARKET_REGIME_OUTER_OBJECT_REQUIRED")
        return value
    except Rejected:
        raise
    except (TypeError, ValueError, UnicodeError, RecursionError, OverflowError):
        raise Rejected("MALFORMED_MARKET_REGIME_OUTER_JSON") from None


def encode_cell(value: object, kind: str) -> object:
    if value is None:
        return None
    if kind == "TIMESTAMP WITH TIME ZONE":
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise Rejected("AWARE_STORED_MARKET_REGIME_INSTANT_REQUIRED")
        return value.astimezone(UTC).isoformat()
    if kind != "VARCHAR" and kind != "JSON" or type(value) is not str:
        raise Rejected("EXACT_STORED_MARKET_REGIME_TEXT_REQUIRED")
    try:
        size = len(value.encode())
    except UnicodeError:
        raise Rejected("MARKET_REGIME_TEXT_ENCODING_INVALID") from None
    if size > MAX_CELL:
        raise Rejected("MARKET_REGIME_TEXT_CELL_BOUND")
    return value


def _row(row: object) -> list[object]:
    if type(row) is not list or len(row) != len(SCHEMA):
        raise Rejected("EXACT_MARKET_REGIME_ROW_SCHEMA_REQUIRED")
    checked: list[object] = []
    for original, (_name, kind) in zip(row, SCHEMA, strict=True):
        value = original
        if original is not None and kind == "TIMESTAMP WITH TIME ZONE":
            if type(original) is not str or len(original) > 64:
                raise Rejected("CANONICAL_STORED_MARKET_REGIME_INSTANT_REQUIRED")
            value = datetime.fromisoformat(original)
        if encode_cell(value, kind) != original:
            raise Rejected("CANONICAL_STORED_MARKET_REGIME_CELL_REQUIRED")
        checked.append(original)
    if any(checked[index] is None for index, name in enumerate(SCHEMA) if name[0] in KEY):
        raise Rejected("MARKET_REGIME_COMPOSITE_KEY_UNKNOWN")
    return checked


@dataclass(frozen=True)
class Snapshot:
    snapshot_id: str
    payload: bytes
    row_count: int


def make_snapshot(source_label: str, rows: list[list[object]]) -> Snapshot:
    if not label(source_label):
        raise Rejected("EXPLICIT_MARKET_REGIME_SOURCE_LABEL_REQUIRED")
    if type(rows) is not list or not 1 <= len(rows) <= MAX_ROWS:
        raise Rejected("WHOLE_MARKET_REGIME_TABLE_ROW_BOUND")
    try:
        checked = [_row(row) for row in rows]
        if (
            sum(
                len(value.encode())
                for row in checked
                for index, value in enumerate(row)
                if index != 1 and isinstance(value, str)
            )
            > MAX_BYTES
        ):
            raise Rejected("MARKET_REGIME_TEXT_AGGREGATE_BOUND")
        keys = [
            tuple(row[index] for index, name in enumerate(SCHEMA) if name[0] in KEY)
            for row in checked
        ]
        if len(set(keys)) != len(keys):
            raise Rejected("DUPLICATE_MARKET_REGIME_COMPOSITE_KEY_NO_WINNER")
        ordered = sorted(checked, key=lambda row: canonical(keys[checked.index(row)]))
        raw = canonical(
            dict(
                version=VERSION,
                table=TABLE,
                source_label=source_label,
                schema=SCHEMA,
                key=KEY,
                rows=ordered,
            )
        )
        if len(raw) > MAX_BYTES:
            raise Rejected("MARKET_REGIME_SNAPSHOT_BYTE_BOUND")
        return Snapshot(sha(raw), raw, len(ordered))
    except Rejected:
        raise
    except (ValueError, TypeError, KeyError, UnicodeError, OverflowError, RecursionError):
        raise Rejected("MALFORMED_RETAINED_MARKET_REGIME_ROWS") from None


def replay_snapshot(raw: bytes, *, expected_snapshot_id: str) -> dict[str, Any]:
    document = parse(raw, MAX_BYTES)
    if not pin(expected_snapshot_id) or sha(raw) != expected_snapshot_id:
        raise Rejected("EXACT_MARKET_REGIME_SNAPSHOT_PIN_REQUIRED")
    try:
        if make_snapshot(document["source_label"], document["rows"]).payload != raw:
            raise Rejected("COMPLETE_MARKET_REGIME_SNAPSHOT_REPLAY_MISMATCH")
        return document
    except Rejected:
        raise
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        raise Rejected("MALFORMED_MARKET_REGIME_SNAPSHOT_CONTRACT") from None


def derive_records(
    raw: bytes, *, snapshot_id: str, capture_event_id: str, envelope_hash: str
) -> tuple[bytes, ...]:
    if not pin(capture_event_id) or not pin(envelope_hash):
        raise Rejected("EXACT_MARKET_REGIME_NATIVE_PINS_REQUIRED")
    document = replay_snapshot(raw, expected_snapshot_id=snapshot_id)
    records: list[bytes] = []
    total = 0
    for ordinal, row in enumerate(document["rows"]):
        fields = dict(zip((name for name, _kind in SCHEMA), row, strict=True))
        key = [fields[name] for name in KEY]
        record = canonical(
            dict(
                version=OBSERVATION_VERSION,
                source_label=document["source_label"],
                snapshot_id=snapshot_id,
                capture_event_id=capture_event_id,
                envelope_hash=envelope_hash,
                source_ordinal=ordinal,
                stored_key=key,
                stored_fields=fields,
                classification="RETAINED_LEGACY_MARKET_REGIME_NOT_NATIVE_REGIME_TRUTH",
                stored_ts_instant=fields["ts"],
                source_time_semantics="COMPOSITE_KEY_STORED_INSTANT_ONLY",
                original_timezone_label=None,
                original_availability_at=None,
                regime_label_interpreted=False,
                trend_interpreted=False,
                volatility_interpreted=False,
                iv_interpreted=False,
                features_interpreted=False,
                original_provider_bytes_retained=False,
                overwritten_history_recovered=False,
                original_regime_execution_replayed=False,
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
            raise Rejected("MARKET_REGIME_PROJECTION_BYTE_BOUND")
        records.append(record)
    return tuple(records)
