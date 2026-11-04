"""Native audited all-partition Bronze persistence and exact coverage consumption."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nse_quant.data_platform import legacy_market_partitions as codec
from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.bronze import BronzeEvent, BronzeEventStore

SOURCE = "legacy_market_partition_capture"
COMMAND = "migrate.legacy_market_partitions@1"


def name(conn: Any, schema: str, table: str) -> str:
    row = conn.execute("SELECT current_database()").fetchone()
    if row is None:
        raise codec.PartitionRejected("CATALOG_UNAVAILABLE")
    return ".".join('"' + str(x).replace('"', '""') + '"' for x in (row[0], schema, table))


def _paths(conn: Any) -> set[Path]:
    return {Path(r[2]).resolve() for r in conn.execute("PRAGMA database_list").fetchall() if r[2]}


def _clock(value: Any) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise codec.PartitionRejected("AWARE_IMPORT_OR_RECORDING_TIME_REQUIRED")
    return value.astimezone(UTC).isoformat()


def _config() -> str:
    from nse_quant.data_platform import legacy_market_snapshot as source

    if source.VERSION != "legacy-market-snapshot@1":
        raise codec.PartitionRejected("UNSUPPORTED_LEGACY_CAPTURE_DEPENDENCY")
    return codec.sha(
        codec.canonical(
            [
                codec.VERSION,
                source.VERSION,
                source.SCHEMAS,
                codec.MAX_PARTITIONS,
                codec.ROWS_PER_PARTITION,
                codec.MAX_PART_BYTES,
                codec.MAX_ROW_TOTAL_BYTES,
                codec.MAX_ARTIFACT_BYTES,
            ]
        )
    )


def _scope(table: str, label: str, capture_id: str) -> str:
    return codec.sha(codec.canonical([codec.VERSION, table, label, capture_id]))


def _events(capture: codec.PartitionCapture, scope: str, at: datetime) -> tuple[BronzeEvent, ...]:
    return tuple(
        BronzeEvent(SOURCE, scope, record, at, payload, codec.VERSION, "legacy_snapshot")
        for record, payload in (
            ("manifest", capture.manifest),
            *((f"part-{i:04d}", raw) for i, raw in enumerate(capture.partitions)),
        )
    )


def preserve_partitioned_legacy_table(
    source: Any,
    bronze: Any,
    *,
    table: str,
    source_label: str,
    expected_capture_id: str,
    imported_at: datetime,
    actor_id: str,
    code_revision: str,
) -> dict[str, Any]:
    """Fresh actual SQL captures; no caller partition-result import or partial commits."""
    if (
        not codec.pin(expected_capture_id)
        or type(actor_id) is not str
        or not 1 <= len(actor_id) <= 128
        or actor_id != actor_id.strip()
        or any(ord(c) < 32 for c in actor_id)
        or type(code_revision) is not str
        or re.fullmatch(r"[a-f0-9]{40}", code_revision) is None
        or table not in codec.KEYS
        or type(source_label) is not str
        or re.fullmatch(r"[A-Za-z0-9_-]{1,64}", source_label) is None
    ):
        raise codec.PartitionRejected("EXPLICIT_REVIEWED_PARTITION_REQUEST_REQUIRED")
    _clock(imported_at)
    if not _paths(bronze):
        raise codec.PartitionRejected("FILE_BACKED_NATIVE_TARGET_REQUIRED")
    if source is bronze or any(
        a == b or a.samefile(b) for a in _paths(source) for b in _paths(bronze)
    ):
        raise codec.PartitionRejected("SEPARATE_NATIVE_TARGET_REQUIRED")
    store = BronzeEventStore(bronze)
    store.verify_target()
    scope = _scope(table, source_label, expected_capture_id)
    jobs = name(bronze, "medallion_audit", "jobs")
    if (
        bronze.execute(
            f"SELECT 1 FROM {jobs} WHERE scope_ref=? LIMIT 1", ["sha256:" + scope]
        ).fetchone()
        or bronze.execute(
            f"SELECT 1 FROM {store.object_name('ingest_batches')} WHERE batch_key=? LIMIT 1",
            [scope],
        ).fetchone()
        or bronze.execute(
            f"SELECT 1 FROM {store.object_name('event_variants')} "
            "WHERE capture_session_id=? LIMIT 1",
            [scope],
        ).fetchone()
    ):
        raise codec.PartitionRejected("FIRST_WRITE_ORIGINAL_PARTITION_OBLIGATION")
    if bronze.execute(
        f"SELECT 1 FROM {store.object_name('input_artifacts')} WHERE artifact_hash=? LIMIT 1",
        [expected_capture_id],
    ).fetchone():
        raise codec.PartitionRejected("ORIGINAL_PARTITION_ARTIFACT_NOT_ADOPTABLE")
    job = AuditLedger(bronze).plan_job(
        command_name=COMMAND,
        actor_id=actor_id,
        scope_ref="sha256:" + scope,
        code_revision=code_revision,
        config_hash=_config(),
    )
    with AuditLedger(bronze).execution(job):
        first = codec.capture_partitioned_legacy_table(
            source, table=table, source_label=source_label
        )
        if first.capture_id != expected_capture_id:
            raise codec.PartitionRejected("REVIEWED_WHOLE_TABLE_CHANGED")
        second = codec.capture_partitioned_legacy_table(
            source, table=table, source_label=source_label
        )
        if first != second:
            raise codec.PartitionRejected("WHOLE_TABLE_CHANGED_DURING_CAPTURE")
        codec.replay_partition_capture(first.artifact, expected_capture_id=expected_capture_id)
        events = _events(first, scope, imported_at)
        result = store.append_batch(
            events, batch_key=scope, input_artifact=first.artifact, job_id=job
        )
        if (
            result.inserted_variants != len(events)
            or result.exact_retries
            or result.conflict_variants
            or result.already_committed
        ):
            raise codec.PartitionRejected("UNEXPECTED_NATIVE_PARTITION_BATCH_REUSE")
    recording = _observe(
        bronze, capture_id=expected_capture_id, table=table, source_label=source_label
    )
    return dict(
        capture_id=expected_capture_id,
        table=table,
        source_label=source_label,
        scope_id=scope,
        partition_count=len(first.partitions),
        row_count=first.row_count,
        job_id=job,
        recording_fingerprint=recording.recording_fingerprint,
        decision_eligibility_asserted=False,
    )


@dataclass(frozen=True)
class NativePartitionRecording:
    capture: codec.PartitionCapture
    recording_fingerprint: str
    original_recording_verified: bool = True
    current_legacy_source_checked: bool = False
    decision_eligibility_asserted: bool = False


def _observe(
    bronze: Any,
    *,
    capture_id: str,
    table: str,
    source_label: str,
) -> NativePartitionRecording:
    if (
        not codec.pin(capture_id)
        or table not in codec.KEYS
        or type(source_label) is not str
        or re.fullmatch(r"[A-Za-z0-9_-]{1,64}", source_label) is None
    ):
        raise codec.PartitionRejected("EXACT_PARTITION_RECORDING_REQUEST_REQUIRED")
    scope = _scope(table, source_label, capture_id)
    store = BronzeEventStore(bronze)
    store.verify_target()
    variants = store.object_name("event_variants")
    batches = store.object_name("ingest_batches")
    artifacts = store.object_name("input_artifacts")
    jobs = name(bronze, "medallion_audit", "jobs")
    history = name(bronze, "medallion_audit", "job_events")
    bronze.execute("BEGIN TRANSACTION")
    try:
        artifact = bronze.execute(
            f"SELECT CASE WHEN octet_length(artifact_bytes)<=? THEN artifact_bytes END,"
            f"recorded_at,first_job_id FROM {artifacts} WHERE artifact_hash=?",
            [codec.MAX_ARTIFACT_BYTES, capture_id],
        ).fetchone()
        if artifact is None or artifact[0] is None:
            raise codec.PartitionRejected("ORIGINAL_PARTITION_ARTIFACT_MISSING_OR_UNBOUNDED")
        capture = codec.replay_partition_capture(bytes(artifact[0]), expected_capture_id=capture_id)
        manifest = json.loads(capture.manifest)
        from nse_quant.data_platform import legacy_market_snapshot as source

        if manifest["schema"] != [list(s) for s in source.SCHEMAS[table]]:
            raise codec.PartitionRejected("NATIVE_PARTITION_SCHEMA_MISMATCH")
        if manifest["table"] != table or manifest["source_label"] != source_label:
            raise codec.PartitionRejected("EXACT_PARTITION_SUBJECT_MISMATCH")
        rows = bronze.execute(
            f"SELECT capture_event_id,envelope_hash,ingest_sequence,source,capture_session_id,"
            f"source_record_id,received_at,recorded_at,exchange_ts,"
            f"CASE WHEN octet_length(payload)<=? THEN payload END,payload_hash,payload_format,"
            f"origin_kind,CASE WHEN length(envelope_json)<=8192 THEN envelope_json END,"
            f"first_batch_key,first_job_id FROM {variants} WHERE capture_session_id=? "
            "ORDER BY source_record_id LIMIT ?",
            [codec.MAX_PART_BYTES, scope, codec.MAX_PARTITIONS + 2],
        ).fetchall()
        scoped = bronze.execute(
            f"SELECT * FROM {jobs} WHERE scope_ref=? ORDER BY job_id LIMIT 3",
            ["sha256:" + scope],
        ).fetchall()
        audit = bronze.execute(
            f"SELECT * FROM {history} WHERE job_id=? ORDER BY event_index LIMIT 5",
            [artifact[2]],
        ).fetchall()
        batch = bronze.execute(f"SELECT * FROM {batches} WHERE batch_key=?", [scope]).fetchone()
        for row in rows:
            count = bronze.execute(
                f"SELECT count(*) FROM {variants} WHERE capture_event_id=?",
                [row[0]],
            ).fetchone()
            if count != (1,):
                raise codec.PartitionRejected("PARTITION_EVENT_VARIANT_AMBIGUITY")
        bronze.execute("COMMIT")
    except BaseException:
        bronze.execute("ROLLBACK")
        raise
    if len(rows) != len(capture.partitions) + 1 or not rows:
        raise codec.PartitionRejected("COMPLETE_PARTITION_EVENT_COVERAGE_REQUIRED")
    expected = _events(capture, scope, rows[0][6])
    expected_by_record = {e.source_record_id: e for e in expected}
    for row in rows:
        event = expected_by_record.get(row[5])
        if (
            event is None
            or row[9] is None
            or bytes(row[9]) != event.payload
            or row[0:2] != (event.capture_event_id, event.envelope_hash)
            or row[3:7] != (SOURCE, scope, event.source_record_id, event.received_at)
            or row[8] is not None
            or row[10:16]
            != (
                event.payload_hash,
                codec.VERSION,
                "legacy_snapshot",
                event.envelope_json,
                scope,
                artifact[2],
            )
        ):
            raise codec.PartitionRejected("COMPLETE_NATIVE_PARTITION_ENVELOPE_MISMATCH")
        _clock(row[7])
    if (
        len(scoped) != 1
        or scoped[0][0] != artifact[2]
        or scoped[0][1] is not None
        or scoped[0][2] != COMMAND
        or not scoped[0][3]
        or re.fullmatch(r"[a-f0-9]{40}", scoped[0][5]) is None
        or scoped[0][6] != _config()
        or len(audit) != 3
        or [(h[1], h[2], h[4]) for h in audit]
        != [(1, "PLANNED", None), (2, "RUNNING", None), (3, "SUCCEEDED", None)]
    ):
        raise codec.PartitionRejected("ORIGINAL_PARTITION_AUDIT_NOT_VERIFIED")
    _clock(scoped[0][7])
    _clock(artifact[1])
    for h in audit:
        _clock(h[3])
    fingerprint = codec.sha(
        codec.canonical(
            dict(
                input_file_hash=capture_id,
                events=[(e.capture_event_id, e.envelope_hash) for e in expected],
            )
        )
    )
    if (
        batch is None
        or batch[0:7] != (scope, fingerprint, capture_id, len(expected), len(expected), 0, 0)
        or batch[8] != artifact[2]
        or batch[7] != max(r[2] for r in rows)
    ):
        raise codec.PartitionRejected("ORIGINAL_PARTITION_BATCH_NOT_VERIFIED")
    _clock(batch[9])
    metadata = [
        codec.VERSION,
        capture_id,
        scope,
        [artifact[1], artifact[2]],
        batch,
        scoped,
        audit,
        [[*r[:9], codec.sha(bytes(r[9])), *r[10:]] for r in rows],
    ]
    raw = json.dumps(
        metadata, sort_keys=True, separators=(",", ":"), allow_nan=False, default=_clock
    ).encode()
    return NativePartitionRecording(capture, codec.sha(raw))


def read_partitioned_legacy_recording(
    bronze: Any,
    *,
    capture_id: str,
    table: str,
    source_label: str,
    expected_recording_fingerprint: str,
) -> NativePartitionRecording:
    """Original native recording verification, not current legacy database verification."""
    if not codec.pin(expected_recording_fingerprint):
        raise codec.PartitionRejected("EXACT_PARTITION_RECORDING_FINGERPRINT_REQUIRED")
    if bronze.execute(
        "SELECT readonly FROM duckdb_databases() WHERE database_name=current_database()"
    ).fetchall() != [(True,)]:
        raise codec.PartitionRejected("READONLY_NATIVE_PARTITION_SOURCE_REQUIRED")
    observed = _observe(bronze, capture_id=capture_id, table=table, source_label=source_label)
    if observed.recording_fingerprint != expected_recording_fingerprint:
        raise codec.PartitionRejected("PARTITION_RECORDING_FINGERPRINT_CHANGED")
    return observed


def revalidate_partitioned_legacy_recording(
    source: Any,
    bronze: Any,
    *,
    capture_id: str,
    table: str,
    source_label: str,
    expected_recording_fingerprint: str,
) -> NativePartitionRecording:
    """Original recording plus repeated current whole-table comparison; no refresh."""
    if source is bronze or any(
        a == b or a.samefile(b) for a in _paths(source) for b in _paths(bronze)
    ):
        raise codec.PartitionRejected("SEPARATE_LEGACY_AND_NATIVE_SOURCES_REQUIRED")
    args = dict(
        capture_id=capture_id,
        table=table,
        source_label=source_label,
        expected_recording_fingerprint=expected_recording_fingerprint,
    )
    first = read_partitioned_legacy_recording(bronze, **args)
    for _ in range(2):
        fresh = codec.capture_partitioned_legacy_table(
            source, table=table, source_label=source_label
        )
        if fresh != first.capture:
            raise codec.PartitionRejected("CURRENT_WHOLE_LEGACY_TABLE_CHANGED")
    second = read_partitioned_legacy_recording(bronze, **args)
    if first != second:
        raise codec.PartitionRejected("NATIVE_RECORDING_CHANGED_DURING_REVALIDATION")
    return replace(second, current_legacy_source_checked=True)
