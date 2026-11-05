"""Bounded retained post-trade-review content; never native outcome truth or admission."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

VERSION = "legacy-post-trade-reviews-snapshot@1"
OBSERVATION_VERSION = "legacy-post-trade-review-observation@1"
TABLE = "post_trade_reviews"
SCHEMA = (
    ("review_id", "VARCHAR"),
    ("ts", "TIMESTAMP WITH TIME ZONE"),
    ("strategy_position_id", "VARCHAR"),
    ("proposal_id", "VARCHAR"),
    ("strategy", "VARCHAR"),
    ("realized_pnl", "DOUBLE"),
    ("exit_reason", "VARCHAR"),
    ("thesis_status", "VARCHAR"),
    ("decision_quality_notes", "VARCHAR"),
    ("outcome_notes", "VARCHAR"),
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
    "whole retained base table; review_id only key; all other fields nullable",
    "stored TIMESTAMPTZ instant or unknown; finite binary64 hex; no outcome truth",
    "no recovered overwritten history, P&L interpretation, execution replay or admission",
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
    raise Rejected("NONFINITE_POST_TRADE_REVIEW_OUTER_JSON")


def parse(raw: bytes, maximum: int) -> dict[str, Any]:
    if type(raw) is not bytes or not 0 < len(raw) <= maximum:
        raise Rejected("POST_TRADE_REVIEW_CONTENT_BYTE_BOUND")
    try:
        value = json.loads(raw, parse_constant=_invalid)
        if type(value) is not dict or canonical(value) != raw:
            raise Rejected("EXACT_CANONICAL_POST_TRADE_REVIEW_OUTER_OBJECT_REQUIRED")
        return value
    except Rejected:
        raise
    except (TypeError, ValueError, UnicodeError, RecursionError, OverflowError):
        raise Rejected("MALFORMED_POST_TRADE_REVIEW_OUTER_JSON") from None


def encode_cell(value: object, kind: str) -> object:
    if value is None:
        return None
    if kind == "TIMESTAMP WITH TIME ZONE":
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise Rejected("AWARE_STORED_POST_TRADE_REVIEW_INSTANT_REQUIRED")
        return value.astimezone(UTC).isoformat()
    if kind == "DOUBLE":
        if type(value) is not float or value.hex() != value.hex():
            raise Rejected("FINITE_STORED_POST_TRADE_REVIEW_BINARY64_REQUIRED")
        return value.hex()
    if kind != "VARCHAR" or type(value) is not str:
        raise Rejected("EXACT_STORED_POST_TRADE_REVIEW_TEXT_REQUIRED")
    try:
        size = len(value.encode())
    except UnicodeError:
        raise Rejected("POST_TRADE_REVIEW_TEXT_ENCODING_INVALID") from None
    if size > MAX_CELL:
        raise Rejected("POST_TRADE_REVIEW_TEXT_CELL_BOUND")
    return value


def _row(row: object) -> list[object]:
    if type(row) is not list or len(row) != len(SCHEMA):
        raise Rejected("EXACT_POST_TRADE_REVIEW_ROW_SCHEMA_REQUIRED")
    checked: list[object] = []
    for original, (_name, kind) in zip(row, SCHEMA, strict=True):
        value = original
        if original is not None and kind == "TIMESTAMP WITH TIME ZONE":
            if type(original) is not str or len(original) > 64:
                raise Rejected("CANONICAL_STORED_POST_TRADE_REVIEW_INSTANT_REQUIRED")
            value = datetime.fromisoformat(original)
        elif original is not None and kind == "DOUBLE":
            if type(original) is not str or len(original) > 64:
                raise Rejected("CANONICAL_STORED_POST_TRADE_REVIEW_BINARY64_REQUIRED")
            value = float.fromhex(original)
        if encode_cell(value, kind) != original:
            raise Rejected("CANONICAL_STORED_POST_TRADE_REVIEW_CELL_REQUIRED")
        checked.append(original)
    if checked[0] is None:
        raise Rejected("POST_TRADE_REVIEW_PRIMARY_KEY_UNKNOWN")
    return checked


@dataclass(frozen=True)
class Snapshot:
    snapshot_id: str
    payload: bytes
    row_count: int


def make_snapshot(source_label: str, rows: list[list[object]]) -> Snapshot:
    if not label(source_label):
        raise Rejected("EXPLICIT_POST_TRADE_REVIEW_SOURCE_LABEL_REQUIRED")
    if type(rows) is not list or not 1 <= len(rows) <= MAX_ROWS:
        raise Rejected("WHOLE_POST_TRADE_REVIEW_TABLE_ROW_BOUND")
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
            raise Rejected("POST_TRADE_REVIEW_TEXT_AGGREGATE_BOUND")
        keys = [row[0] for row in checked]
        if len(set(keys)) != len(keys):
            raise Rejected("DUPLICATE_POST_TRADE_REVIEW_PRIMARY_KEY_NO_WINNER")
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
            raise Rejected("POST_TRADE_REVIEW_SNAPSHOT_BYTE_BOUND")
        return Snapshot(sha(raw), raw, len(ordered))
    except Rejected:
        raise
    except (ValueError, TypeError, KeyError, UnicodeError, OverflowError, RecursionError):
        raise Rejected("MALFORMED_RETAINED_POST_TRADE_REVIEW_ROWS") from None


def replay_snapshot(raw: bytes, *, expected_snapshot_id: str) -> dict[str, Any]:
    document = parse(raw, MAX_BYTES)
    if not pin(expected_snapshot_id) or sha(raw) != expected_snapshot_id:
        raise Rejected("EXACT_POST_TRADE_REVIEW_SNAPSHOT_PIN_REQUIRED")
    try:
        if make_snapshot(document["source_label"], document["rows"]).payload != raw:
            raise Rejected("COMPLETE_POST_TRADE_REVIEW_SNAPSHOT_REPLAY_MISMATCH")
        return document
    except Rejected:
        raise
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        raise Rejected("MALFORMED_POST_TRADE_REVIEW_SNAPSHOT_CONTRACT") from None


def derive_records(
    raw: bytes, *, snapshot_id: str, capture_event_id: str, envelope_hash: str
) -> tuple[bytes, ...]:
    if not pin(capture_event_id) or not pin(envelope_hash):
        raise Rejected("EXACT_POST_TRADE_REVIEW_NATIVE_PINS_REQUIRED")
    document = replay_snapshot(raw, expected_snapshot_id=snapshot_id)
    records: list[bytes] = []
    total = 0
    for ordinal, row in enumerate(document["rows"]):
        fields = dict(zip((name for name, _kind in SCHEMA), row, strict=True))
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
                classification="RETAINED_LEGACY_POST_TRADE_REVIEW_NOT_NATIVE_OUTCOME_TRUTH",
                stored_ts_instant=fields["ts"],
                source_time_semantics="NULL_OR_LEGACY_STORED_INSTANT_ONLY",
                original_timezone_label=None,
                original_availability_at=None,
                exit_reason_semantics="RETAINED_LEGACY_LABEL_NOT_NATIVE_EXIT_TRUTH",
                thesis_status_semantics="RETAINED_LEGACY_LABEL_NOT_NATIVE_OUTCOME_TRUTH",
                pnl_interpreted=False,
                notes_interpreted=False,
                original_provider_bytes_retained=False,
                overwritten_history_recovered=False,
                original_review_execution_replayed=False,
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
            raise Rejected("POST_TRADE_REVIEW_PROJECTION_BYTE_BOUND")
        records.append(record)
    return tuple(records)
