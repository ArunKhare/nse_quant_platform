"""Shared strict Silver persistence helpers for new-series Bronze recordings."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

Rejected = ValueError


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def pin(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def actor(value: object) -> bool:
    return type(value) is str and 0 < len(value.encode()) <= 128


def revision(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[a-f0-9]{40}", value) is not None


def clock(value: object) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise Rejected("AWARE_SILVER_CLOCK_REQUIRED")
    return value.astimezone(datetime.now().astimezone().tzinfo)


def separate(source: Any, target: Any) -> None:
    if source is target:
        raise Rejected("SEPARATE_TARGET_REQUIRED")


def readonly(connection: Any) -> None:
    if connection.execute(
        "SELECT readonly FROM duckdb_databases() WHERE database_name=current_database()"
    ).fetchall() != [(True,)]:
        raise Rejected("READONLY_SILVER_READER_REQUIRED")


def metadata(
    connection: Any, sql: str, parameters: list[Any], expected: int
) -> list[tuple[Any, ...]]:
    connection.execute("BEGIN TRANSACTION")
    try:
        rows = connection.execute(sql, parameters).fetchall()
        connection.execute("COMMIT")
    except BaseException:
        connection.execute("ROLLBACK")
        raise
    if len(rows) != expected:
        raise Rejected("SILVER_METADATA_COVERAGE_MISMATCH")
    return rows


@dataclass(frozen=True)
class SilverPins:
    source_label: str
    snapshot_id: str
    capture_event_id: str
    envelope_hash: str
    recording_fingerprint: str

    @property
    def scope_id(self) -> str:
        return sha(canonical([self.source_label]))

    def reader_args(self) -> dict[str, str]:
        return dict(
            source_label=self.source_label,
            snapshot_id=self.snapshot_id,
            capture_event_id=self.capture_event_id,
            envelope_hash=self.envelope_hash,
            expected_recording_fingerprint=self.recording_fingerprint,
        )
