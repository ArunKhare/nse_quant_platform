"""Audited bounded retained daily-RV SQL evidence; no provider or decision claims."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from nse_quant.data_platform import legacy_daily_rv as codec
from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.bronze import BronzeEvent, BronzeEventStore

VERSION = "legacy-daily-rv-bronze-recording@1"
COMMAND = "migrate.legacy_daily_rv_snapshot@1"
SOURCE = "legacy_daily_rv_table_snapshot"
DEFINITION = (
    VERSION,
    COMMAND,
    SOURCE,
    codec.DEFINITION,
    "scope=profile+source label; reviewed pins never heal failed scope",
)
MAX_METADATA = 32768


def name(conn: Any, schema: str, table: str) -> str:
    row = conn.execute("SELECT current_database()").fetchone()
    if row is None:
        raise codec.Rejected("CATALOG_UNAVAILABLE")
    return ".".join('"' + str(x).replace('"', '""') + '"' for x in (row[0], schema, table))


def _clock(value: Any) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise codec.Rejected("AWARE_IMPORT_CLOCK_REQUIRED")
    return value.astimezone(UTC).isoformat()


def _json(value: object) -> bytes:
    import json

    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=_clock
    ).encode()


def _readonly(conn: Any) -> None:
    if conn.execute(
        "SELECT readonly FROM duckdb_databases() WHERE database_name=current_database()"
    ).fetchall() != [(True,)]:
        raise codec.Rejected("READONLY_SOURCE_REQUIRED")


def _paths(conn: Any) -> set[Path]:
    return {Path(r[2]).resolve() for r in conn.execute("PRAGMA database_list").fetchall() if r[2]}


def _separate(source: Any, target: Any) -> None:
    if not _paths(target):
        raise codec.Rejected("FILE_BACKED_TARGET_REQUIRED")
    if source is target or any(
        a == b or a.samefile(b) for a in _paths(source) for b in _paths(target)
    ):
        raise codec.Rejected("SEPARATE_TARGET_REQUIRED")


def scope_id(source_label: str) -> str:
    if not codec.label(source_label):
        raise codec.Rejected("EXPLICIT_SOURCE_LABEL_REQUIRED")
    return codec.sha(codec.canonical([VERSION, source_label]))


def capture_daily_rv(source: Any, *, source_label: str) -> codec.Snapshot:
    """Owned read-only connection, no outer transaction; entire exact-schema table.

    SQL bounds bound transfer, not scan cost or process memory. DATE remains a
    stored label. A capture is not recovered original provider bytes or history.
    """
    scope_id(source_label)
    _readonly(source)
    table = name(source, "main", codec.TABLE)
    source.execute("BEGIN TRANSACTION")
    try:
        schema = source.execute(
            "SELECT column_name,data_type FROM information_schema.columns "
            "WHERE table_catalog=current_database() AND table_schema='main' AND table_name=? "
            "ORDER BY ordinal_position LIMIT 6",
            [codec.TABLE],
        ).fetchall()
        objects = source.execute(
            "SELECT table_type FROM information_schema.tables WHERE table_catalog="
            "current_database() AND table_schema='main' AND table_name=?",
            [codec.TABLE],
        ).fetchall()
        if tuple(schema) != codec.SCHEMA or objects != [("BASE TABLE",)]:
            raise codec.Rejected("EXACT_LEGACY_SCHEMA_REQUIRED")
        # Preflight before transferring any text. Same transaction as row read.
        totals = source.execute(
            f"SELECT count(*),coalesce(sum(octet_length(encode(symbol))),0),"
            f"coalesce(max(octet_length(encode(symbol))),0) FROM {table}"
        ).fetchone()
        if totals is None or not 1 <= totals[0] <= codec.MAX_ROWS:
            raise codec.Rejected("WHOLE_TABLE_ROW_BOUND")
        if totals[2] > codec.MAX_CELL or totals[1] > codec.MAX_BYTES:
            raise codec.Rejected("TEXT_TRANSFER_BOUND")
        records = source.execute(
            f"SELECT CASE WHEN octet_length(encode(symbol))<=? THEN symbol END,"
            f"trading_date,rv,observation_count FROM {table} LIMIT ?",
            [codec.MAX_CELL, codec.MAX_ROWS + 1],
        ).fetchall()
        if len(records) != totals[0]:
            raise codec.Rejected("WHOLE_TABLE_ROW_BOUND")
        encoded: list[list[str]] = []
        for symbol, day, rv, count in records:
            if (
                type(symbol) is not str
                or type(day) is not date
                or type(rv) is not float
                or type(count) is not int
            ):
                raise codec.Rejected("EXACT_NON_NULL_SQL_TYPES_REQUIRED")
            encoded.append([symbol, day.isoformat(), rv.hex(), str(count)])
        snapshot = codec.make_snapshot(source_label, encoded)
        source.execute("COMMIT")
        return snapshot
    except BaseException:
        source.execute("ROLLBACK")
        raise


def _metadata(conn: Any, sql: str, args: list[object], maximum: int) -> list[Any]:
    rows = conn.execute(sql, args).fetchmany(maximum + 1)
    if len(rows) > maximum or len(_json(rows)) > MAX_METADATA:
        raise codec.Rejected("RECORDING_METADATA_BOUND")
    return rows


def _recording(
    bronze: Any, *, source_label: str, snapshot_id: str, capture_event_id: str, envelope_hash: str
) -> tuple[str, bytes]:
    if not all(codec.pin(x) for x in (snapshot_id, capture_event_id, envelope_hash)):
        raise codec.Rejected("EXACT_BRONZE_PINS_REQUIRED")
    scope = scope_id(source_label)
    store = BronzeEventStore(bronze)
    store.verify_target()
    variants = store.object_name("event_variants")
    batches = store.object_name("ingest_batches")
    artifacts = store.object_name("input_artifacts")
    jobs = name(bronze, "medallion_audit", "jobs")
    events = name(bronze, "medallion_audit", "job_events")
    bronze.execute("BEGIN TRANSACTION")
    try:
        rows = bronze.execute(
            f"SELECT CASE WHEN length(source)<=128 THEN source END,"
            f"CASE WHEN length(capture_session_id)<=64 THEN capture_session_id END,"
            f"CASE WHEN length(source_record_id)<=128 THEN source_record_id END,"
            f"received_at,recorded_at,"
            f"exchange_ts,CASE WHEN octet_length(payload)<=? THEN payload END,"
            f"CASE WHEN length(payload_hash)<=64 THEN payload_hash END,"
            f"CASE WHEN length(payload_format)<=128 THEN payload_format END,"
            f"CASE WHEN length(origin_kind)<=32 THEN origin_kind END,"
            f"CASE WHEN octet_length(encode(envelope_json))<=8192 "
            f"THEN envelope_json END,CASE WHEN length(first_batch_key)<=64 "
            f"THEN first_batch_key END,CASE WHEN length(first_job_id)<=128 "
            f"THEN first_job_id END,ingest_sequence "
            f"FROM {variants} WHERE capture_event_id=? OR capture_session_id=? LIMIT 3",
            [codec.MAX_BYTES, capture_event_id, scope],
        ).fetchall()
        if len(rows) != 1 or rows[0][6] is None or rows[0][10] is None:
            raise codec.Rejected("EXACT_ORIGINAL_VARIANT_REQUIRED")
        row = rows[0]
        raw = bytes(row[6])
        doc = codec.replay_snapshot(raw, expected_snapshot_id=snapshot_id)
        if doc["source_label"] != source_label:
            raise codec.Rejected("SOURCE_LABEL_MISMATCH")
        event = BronzeEvent(
            SOURCE, scope, codec.TABLE, row[3], raw, codec.VERSION, "legacy_snapshot"
        )
        if (
            row[:4] != (SOURCE, scope, codec.TABLE, row[3])
            or row[5] is not None
            or row[7:12]
            != (snapshot_id, codec.VERSION, "legacy_snapshot", event.envelope_json, scope)
            or event.capture_event_id != capture_event_id
            or event.envelope_hash != envelope_hash
        ):
            raise codec.Rejected("NATIVE_ENVELOPE_BINDING_MISMATCH")
        scoped = _metadata(
            bronze,
            f"SELECT CASE WHEN length(job_id)<=128 THEN job_id END,"
            f"CASE WHEN parent_job_id IS NULL THEN NULL WHEN length(parent_job_id)<=128 "
            f"THEN parent_job_id ELSE 'OVERSIZED' END,"
            f"CASE WHEN length(command_name)<=128 THEN command_name END,"
            f"CASE WHEN length(actor_id)<=128 THEN actor_id END,scope_ref,"
            f"CASE WHEN length(code_revision)<=40 THEN code_revision END,"
            f"CASE WHEN length(config_hash)<=64 THEN config_hash END,created_at "
            f"FROM {jobs} WHERE scope_ref=?",
            ["sha256:" + scope],
            1,
        )
        history = _metadata(
            bronze,
            f"SELECT job_id,event_index,CASE WHEN length(state)<=32 THEN state END,"
            f"recorded_at,CASE WHEN reason_code IS NULL THEN NULL "
            f"WHEN length(reason_code)<=64 THEN reason_code ELSE 'OVERSIZED' END "
            f"FROM {events} "
            "WHERE job_id=? ORDER BY event_index",
            [row[12]],
            3,
        )
        batch = _metadata(
            bronze,
            f"SELECT batch_key,CASE WHEN length(batch_fingerprint)<=64 THEN batch_fingerprint END,"
            f"CASE WHEN length(input_file_hash)<=64 THEN input_file_hash END,"
            f"input_events,inserted_variants,"
            f"exact_retries,conflict_variants,last_sequence,"
            f"CASE WHEN length(job_id)<=128 THEN job_id END,committed_at FROM {batches} "
            "WHERE batch_key=?",
            [scope],
            1,
        )
        artifact = bronze.execute(
            f"SELECT CASE WHEN octet_length(artifact_bytes)<=? THEN artifact_bytes END,"
            f"CASE WHEN length(first_job_id)<=128 THEN first_job_id END,"
            f"recorded_at FROM {artifacts} WHERE artifact_hash=? LIMIT 2",
            [codec.MAX_BYTES, snapshot_id],
        ).fetchall()
        bronze.execute("COMMIT")
    except BaseException:
        bronze.execute("ROLLBACK")
        raise
    config = codec.sha(codec.canonical([DEFINITION, snapshot_id]))
    if (
        len(scoped) != 1
        or scoped[0][0] != row[12]
        or scoped[0][1] is not None
        or scoped[0][2] != COMMAND
        or not _actor(scoped[0][3])
        or scoped[0][4] != "sha256:" + scope
        or not _revision(scoped[0][5])
        or scoped[0][6] != config
        or [(h[0], h[1], h[2], h[4]) for h in history]
        != [
            (row[12], 1, "PLANNED", None),
            (row[12], 2, "RUNNING", None),
            (row[12], 3, "SUCCEEDED", None),
        ]
    ):
        raise codec.Rejected("ORIGINAL_AUDIT_NOT_VERIFIED")
    fingerprint = codec.sha(
        codec.canonical(
            dict(input_file_hash=snapshot_id, events=[(capture_event_id, envelope_hash)])
        )
    )
    if (
        len(batch) != 1
        or batch[0][:9] != (scope, fingerprint, snapshot_id, 1, 1, 0, 0, row[13], row[12])
        or type(row[13]) is not int
        or row[13] <= 0
        or len(artifact) != 1
        or artifact[0][0] is None
        or bytes(artifact[0][0]) != raw
        or artifact[0][1] != row[12]
    ):
        raise codec.Rejected("ORIGINAL_BATCH_OR_ARTIFACT_NOT_VERIFIED")
    context = [
        VERSION,
        list(row[:6]),
        codec.sha(raw),
        list(row[7:]),
        scoped,
        history,
        batch,
        [artifact[0][1], artifact[0][2]],
        codec.sha(codec.canonical(DEFINITION)),
    ]
    for clock in [
        row[3],
        row[4],
        scoped[0][7],
        batch[0][9],
        artifact[0][2],
        *(h[3] for h in history),
    ]:
        _clock(clock)
    return codec.sha(_json(context)), raw


def _actor(value: object) -> bool:
    return (
        type(value) is str
        and 1 <= len(value) <= 128
        and value == value.strip()
        and all(ord(c) >= 32 for c in value)
    )


def _revision(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[a-f0-9]{40}", value) is not None


def preserve_daily_rv(
    source: Any,
    bronze: Any,
    *,
    source_label: str,
    expected_snapshot_id: str,
    imported_at: datetime,
    actor_id: str,
    code_revision: str,
) -> dict[str, Any]:
    """First-write source-label scope, dedicated initialized native Bronze target.

    A changed pin/revision/actor/import clock never heals this scope. No recovery,
    adoption, cutover or real-data release. Owners close before read-only reopen.
    """
    scope = scope_id(source_label)
    if not codec.pin(expected_snapshot_id) or not _revision(code_revision) or not _actor(actor_id):
        raise codec.Rejected("REVIEWED_REQUEST_REQUIRED")
    _clock(imported_at)
    _separate(source, bronze)
    _readonly(source)
    store = BronzeEventStore(bronze)
    store.verify_target()
    for table, column, value in (
        (name(bronze, "medallion_audit", "jobs"), "scope_ref", "sha256:" + scope),
        (store.object_name("event_variants"), "capture_session_id", scope),
        (store.object_name("ingest_batches"), "batch_key", scope),
        (store.object_name("input_artifacts"), "artifact_hash", expected_snapshot_id),
    ):
        if bronze.execute(f'SELECT 1 FROM {table} WHERE "{column}"=? LIMIT 1', [value]).fetchone():
            raise codec.Rejected("FIRST_WRITE_ORIGINAL_OBLIGATION")
    ledger = AuditLedger(bronze)
    job = ledger.plan_job(
        command_name=COMMAND,
        actor_id=actor_id,
        scope_ref="sha256:" + scope,
        code_revision=code_revision,
        config_hash=codec.sha(codec.canonical([DEFINITION, expected_snapshot_id])),
    )
    with ledger.execution(job):
        first = capture_daily_rv(source, source_label=source_label)
        if first.snapshot_id != expected_snapshot_id:
            raise codec.Rejected("REVIEWED_SOURCE_CHANGED")
        second = capture_daily_rv(source, source_label=source_label)
        if first != second:
            raise codec.Rejected("SOURCE_CHANGED_DURING_CAPTURE")
        codec.replay_snapshot(first.payload, expected_snapshot_id=expected_snapshot_id)
        event = BronzeEvent(
            SOURCE, scope, codec.TABLE, imported_at, first.payload, codec.VERSION, "legacy_snapshot"
        )
        receipt = store.append_batch(
            (event,), batch_key=scope, input_artifact=first.payload, job_id=job
        )
        if (
            receipt.inserted_variants != 1
            or receipt.exact_retries
            or receipt.conflict_variants
            or receipt.already_committed
        ):
            raise codec.Rejected("UNEXPECTED_NATIVE_BATCH_REUSE")
    recording, _raw = _recording(
        bronze,
        source_label=source_label,
        snapshot_id=expected_snapshot_id,
        capture_event_id=event.capture_event_id,
        envelope_hash=event.envelope_hash,
    )
    return dict(
        snapshot_id=expected_snapshot_id,
        source_label=source_label,
        capture_event_id=event.capture_event_id,
        envelope_hash=event.envelope_hash,
        recording_fingerprint=recording,
        row_count=first.row_count,
        job_id=job,
        decision_eligibility_asserted=False,
    )


def read_daily_rv_bronze(
    bronze: Any,
    *,
    source_label: str,
    snapshot_id: str,
    capture_event_id: str,
    envelope_hash: str,
    expected_recording_fingerprint: str,
) -> tuple[bytes, ...]:
    """Original recording verification plus exact projection, not persisted Silver."""
    if not codec.pin(expected_recording_fingerprint):
        raise codec.Rejected("EXACT_RECORDING_PIN_REQUIRED")
    _readonly(bronze)
    fingerprint, raw = _recording(
        bronze,
        source_label=source_label,
        snapshot_id=snapshot_id,
        capture_event_id=capture_event_id,
        envelope_hash=envelope_hash,
    )
    if fingerprint != expected_recording_fingerprint:
        raise codec.Rejected("RECORDING_FINGERPRINT_CHANGED")
    return codec.derive_records(
        raw, snapshot_id=snapshot_id, capture_event_id=capture_event_id, envelope_hash=envelope_hash
    )


def revalidate_daily_rv_source(source: Any, bronze: Any, **pins: Any) -> tuple[bytes, ...]:
    """Separate current SQL equality check bracketed by pinned native reads.

    Sequential observations do not establish an atomic cross-database snapshot.
    """
    _separate(source, bronze)
    first = read_daily_rv_bronze(bronze, **pins)
    for _ in range(2):
        current = capture_daily_rv(source, source_label=pins["source_label"])
        if current.snapshot_id != pins["snapshot_id"]:
            raise codec.Rejected("CURRENT_LEGACY_SOURCE_CHANGED")
    second = read_daily_rv_bronze(bronze, **pins)
    if first != second:
        raise codec.Rejected("NATIVE_RECORDING_CHANGED")
    return second
