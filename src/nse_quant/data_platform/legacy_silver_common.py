"""Shared strict Silver persistence helpers for new-series Bronze recordings."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
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
    source_paths = {
        Path(row[2]).resolve()
        for row in source.execute("PRAGMA database_list").fetchall()
        if row[2]
    }
    target_paths = {
        Path(row[2]).resolve()
        for row in target.execute("PRAGMA database_list").fetchall()
        if row[2]
    }
    if source is target or any(
        source_path == target_path or source_path.samefile(target_path)
        for source_path in source_paths
        for target_path in target_paths
    ):
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
    if expected >= 0 and len(rows) != expected:
        raise Rejected("SILVER_METADATA_COVERAGE_MISMATCH")
    return rows


def verify_recording(
    connection: Any,
    *,
    command: str,
    scope_ref: str,
    config_hash: str,
    revision_id: str,
    sets_table: str,
    observations_table: str,
    attempts_table: str,
    observation_count: int,
) -> None:
    jobs = connection.execute(
        "SELECT job_id,created_at FROM medallion_audit.jobs "
        "WHERE command_name=? AND scope_ref=? AND config_hash=? LIMIT 3",
        [command, scope_ref, config_hash],
    ).fetchall()
    successful = []
    for job_id, created_at in jobs:
        events = connection.execute(
            "SELECT event_index,state,recorded_at FROM medallion_audit.job_events "
            "WHERE job_id=? ORDER BY event_index LIMIT 4",
            [job_id],
        ).fetchall()
        if [(row[0], row[1]) for row in events] == [
            (1, "PLANNED"),
            (2, "RUNNING"),
            (3, "SUCCEEDED"),
        ]:
            successful.append((created_at, *(row[2] for row in events)))
    if len(successful) != 1:
        raise Rejected("SILVER_ORIGINAL_AUDIT_NOT_VERIFIED")

    created_at, planned_at, running_at, succeeded_at = (clock(value) for value in successful[0])
    if not created_at <= planned_at <= running_at <= succeeded_at:
        raise Rejected("SILVER_ORIGINAL_AUDIT_NOT_VERIFIED")

    timestamps = [
        *metadata(
            connection,
            f"SELECT recorded_at FROM {sets_table} WHERE revision_id=?",
            [revision_id],
            1,
        ),
        *metadata(
            connection,
            f"SELECT recorded_at FROM {observations_table} WHERE revision_id=? ORDER BY ordinal",
            [revision_id],
            observation_count,
        ),
        *metadata(
            connection,
            f"SELECT recorded_at FROM {attempts_table} WHERE revision_id=?",
            [revision_id],
            1,
        ),
    ]
    if any(not running_at <= clock(row[0]) <= succeeded_at for row in timestamps):
        raise Rejected("SILVER_RECORDED_AT_OUTSIDE_AUDIT_INTERVAL")


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
