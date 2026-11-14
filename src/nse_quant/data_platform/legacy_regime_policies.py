"""Bounded retained regime-policy content; never native policy truth or execution permission."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

VERSION = "legacy-regime-policies-snapshot@1"
OBSERVATION_VERSION = "legacy-regime-policy-observation@1"
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
RISK_BEFORE_CLOCK = "RISK_BEFORE_CLOCK"
CLOCK_BEFORE_RISK = "CLOCK_BEFORE_RISK"


_LAYOUTS = {
    RISK_BEFORE_CLOCK: SCHEMA,
    CLOCK_BEFORE_RISK: (
        *SCHEMA[:9],
        SCHEMA[10],  # created_at
        SCHEMA[9],  # risk_limits
    ),
}


def checked_layout(layout_id: str) -> tuple[tuple[str, str], ...]:
    try:
        return _LAYOUTS[layout_id]
    except KeyError:
        raise Rejected("UNKNOWN_REGIME_POLICY_LAYOUT") from None


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
    "whole retained base table; policy_id only key; all other fields nullable",
    "stored TIMESTAMPTZ instant or unknown; DATE retained calendar date only",
    "opaque JSON CAST(JSON AS VARCHAR); SQL NULL distinct from JSON null",
    "no recovered overwritten history, policy truth, execution replay or admission",
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
            raise Rejected("DUPLICATE_REGIME_POLICY_OUTER_JSON_KEY")
        result[key] = value
    return result


def _invalid(_value: str) -> Any:
    raise Rejected("NONFINITE_REGIME_POLICY_OUTER_JSON")


def parse(raw: bytes, maximum: int) -> dict[str, Any]:
    if type(raw) is not bytes or not 0 < len(raw) <= maximum:
        raise Rejected("REGIME_POLICY_CONTENT_BYTE_BOUND")
    try:
        value = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_invalid)
        if type(value) is not dict or canonical(value) != raw:
            raise Rejected("EXACT_CANONICAL_REGIME_POLICY_OUTER_OBJECT_REQUIRED")
        return value
    except Rejected:
        raise
    except (TypeError, ValueError, UnicodeError, RecursionError, OverflowError):
        raise Rejected("MALFORMED_REGIME_POLICY_OUTER_JSON") from None


def encode_cell(value: object, kind: str) -> object:
    if value is None:
        return None
    if kind == "TIMESTAMP WITH TIME ZONE":
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise Rejected("AWARE_STORED_REGIME_POLICY_INSTANT_REQUIRED")
        return value.astimezone(UTC).isoformat()
    if kind == "DATE":
        if type(value) is not date:
            raise Rejected("EXACT_STORED_REGIME_POLICY_DATE_REQUIRED")
        return value.isoformat()
    if kind != "VARCHAR" and kind != "JSON" or type(value) is not str:
        raise Rejected("EXACT_STORED_REGIME_POLICY_TEXT_REQUIRED")
    try:
        size = len(value.encode())
    except UnicodeError:
        raise Rejected("REGIME_POLICY_TEXT_ENCODING_INVALID") from None
    if size > MAX_CELL:
        raise Rejected("REGIME_POLICY_TEXT_CELL_BOUND")
    return value


def _row(row: object) -> list[object]:
    if type(row) is not list or len(row) != len(SCHEMA):
        raise Rejected("EXACT_REGIME_POLICY_ROW_SCHEMA_REQUIRED")

    checked: list[object] = []
    for original, (_name, kind) in zip(row, SCHEMA, strict=True):
        value = original

        if original is not None and kind == "DATE":
            if type(original) is not str or len(original) != 10:
                raise Rejected("CANONICAL_STORED_REGIME_POLICY_DATE_REQUIRED")
            value = date.fromisoformat(original)
        elif original is not None and kind == "TIMESTAMP WITH TIME ZONE":
            if type(original) is not str or len(original) > 64:
                raise Rejected("CANONICAL_STORED_REGIME_POLICY_INSTANT_REQUIRED")
            value = datetime.fromisoformat(original)

        if encode_cell(value, kind) != original:
            raise Rejected("CANONICAL_STORED_REGIME_POLICY_CELL_REQUIRED")

        checked.append(original)

    if checked[0] is None:
        raise Rejected("REGIME_POLICY_PRIMARY_KEY_UNKNOWN")

    return checked


@dataclass(frozen=True)
class Snapshot:
    snapshot_id: str
    payload: bytes
    row_count: int


def make_snapshot(
    source_label: str,
    rows: list[list[object]],
    *,
    layout_id: str = RISK_BEFORE_CLOCK,
) -> Snapshot:
    layout = checked_layout(layout_id)

    if not label(source_label):
        raise Rejected("EXPLICIT_REGIME_POLICY_SOURCE_LABEL_REQUIRED")
    if type(rows) is not list or not 1 <= len(rows) <= MAX_ROWS:
        raise Rejected("WHOLE_REGIME_POLICY_TABLE_ROW_BOUND")

    try:
        checked = [_row(row) for row in rows]
        created_index = next(
            index for index, (name, _kind) in enumerate(SCHEMA) if name == "created_at"
        )

        if (
            sum(
                len(value.encode())
                for row in checked
                for index, value in enumerate(row)
                if index != created_index and isinstance(value, str)
            )
            > MAX_BYTES
        ):
            raise Rejected("REGIME_POLICY_TEXT_AGGREGATE_BOUND")

        keys = [row[0] for row in checked]
        if len(set(keys)) != len(keys):
            raise Rejected("DUPLICATE_REGIME_POLICY_PRIMARY_KEY_NO_WINNER")

        ordered = sorted(checked, key=lambda row: canonical(row[0]))
        raw = canonical(
            dict(
                version=VERSION,
                table=TABLE,
                source_label=source_label,
                layout_id=layout_id,
                physical_columns=layout,
                rows=ordered,
            )
        )

        if len(raw) > MAX_BYTES:
            raise Rejected("REGIME_POLICY_SNAPSHOT_BYTE_BOUND")

        return Snapshot(sha(raw), raw, len(ordered))
    except Rejected:
        raise
    except (
        ValueError,
        TypeError,
        KeyError,
        UnicodeError,
        OverflowError,
        RecursionError,
    ):
        raise Rejected("MALFORMED_RETAINED_REGIME_POLICY_ROWS") from None


def replay_snapshot(raw: bytes, *, expected_snapshot_id: str) -> dict[str, Any]:
    document = parse(raw, MAX_BYTES)

    if not pin(expected_snapshot_id) or sha(raw) != expected_snapshot_id:
        raise Rejected("EXACT_REGIME_POLICY_SNAPSHOT_PIN_REQUIRED")

    layout_id = document.get("layout_id")
    if layout_id not in _LAYOUTS:
        raise Rejected("UNKNOWN_REGIME_POLICY_LAYOUT")

    expected_columns = [list(item) for item in checked_layout(layout_id)]
    if document.get("physical_columns") != expected_columns:
        raise Rejected("COMPLETE_POLICY_REPLAY_MISMATCH")

    try:
        replayed = make_snapshot(
            document["source_label"],
            document["rows"],
            layout_id=layout_id,
        )
        if replayed.payload != raw:
            raise Rejected("COMPLETE_REGIME_POLICY_SNAPSHOT_REPLAY_MISMATCH")
        return document
    except Rejected:
        raise
    except (
        ValueError,
        TypeError,
        KeyError,
        OverflowError,
        RecursionError,
    ):
        raise Rejected("MALFORMED_REGIME_POLICY_SNAPSHOT_CONTRACT") from None


def derive_records(
    raw: bytes,
    *,
    snapshot_id: str,
    capture_event_id: str,
    envelope_hash: str,
) -> tuple[bytes, ...]:
    if not pin(capture_event_id) or not pin(envelope_hash):
        raise Rejected("EXACT_REGIME_POLICY_NATIVE_PINS_REQUIRED")

    document = replay_snapshot(raw, expected_snapshot_id=snapshot_id)
    layout = checked_layout(document["layout_id"])
    _ = [name for name, _kind in layout]
    records: list[bytes] = []
    total = 0

    for ordinal, row in enumerate(document["rows"]):
        fields = dict(zip((name for name, _kind in SCHEMA), row, strict=True))

        flags: list[str] = []

        if (
            fields["train_start"] is not None
            and fields["train_end"] is not None
            and fields["train_start"] > fields["train_end"]
        ):
            flags.append("REVERSED_STORED_TRAIN_DATES")

        if (
            fields["test_start"] is not None
            and fields["test_end"] is not None
            and fields["test_start"] > fields["test_end"]
        ):
            flags.append("REVERSED_STORED_TEST_DATES")

        record = canonical(
            dict(
                version=OBSERVATION_VERSION,
                source_label=document["source_label"],
                source_layout_id=document["layout_id"],
                snapshot_id=snapshot_id,
                capture_event_id=capture_event_id,
                envelope_hash=envelope_hash,
                source_ordinal=ordinal,
                stored_key=[row[0]],
                stored_fields=fields,
                flags=flags,
                classification=("RETAINED_LEGACY_REGIME_POLICY_NOT_NATIVE_POLICY_TRUTH"),
                stored_created_instant=fields["created_at"],
                source_time_semantics="NULL_OR_LEGACY_STORED_INSTANT_ONLY",
                original_timezone_label=None,
                original_availability_at=None,
                selection_status_semantics=("RETAINED_LEGACY_LABEL_NOT_NATIVE_POLICY_TRUTH"),
                allowed_regimes_interpreted=False,
                regime_metrics_interpreted=False,
                risk_limits_interpreted=False,
                original_provider_bytes_retained=False,
                overwritten_history_recovered=False,
                original_policy_execution_replayed=False,
                native_decision_replayed=False,
                policy_authorized=False,
                policy_json_interpreted=False,
                training_causality_verified=False,
                canonical_contract_id=None,
                availability_evidence_verified=False,
                economic_validity_verified=False,
                publication_asserted=False,
                decision_eligibility_asserted=False,
            )
        )

        total += len(record)
        if len(record) > MAX_RECORD or total > MAX_RECORDS:
            raise Rejected("REGIME_POLICY_PROJECTION_BYTE_BOUND")

        records.append(record)

    return tuple(records)
