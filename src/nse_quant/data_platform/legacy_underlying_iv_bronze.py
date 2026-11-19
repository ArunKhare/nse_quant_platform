"""Actual audited native Bronze preservation of bounded retained underlying-IV SQL."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from nse_quant.data_platform import legacy_daily_rv_bronze as common
from nse_quant.data_platform import legacy_underlying_iv as codec
from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.bronze import BronzeEvent, BronzeEventStore

VERSION = "legacy-underlying-iv-bronze-recording@1"
COMMAND = "migrate.legacy_underlying_iv_snapshot@1"
SOURCE = "legacy_underlying_iv_table_snapshot"
DEFINITION = (
    VERSION,
    COMMAND,
    SOURCE,
    codec.DEFINITION,
    "source-label first write; no recovery/adoption or original provider claim",
)


def scope_id(source_label: str) -> str:
    if not codec.label(source_label):
        raise codec.Rejected("EXPLICIT_SOURCE_LABEL_REQUIRED")
    return codec.sha(codec.canonical([VERSION, source_label]))


def capture_underlying_iv(source: Any, *, source_label: str) -> codec.Snapshot:
    scope_id(source_label)
    common._readonly(source)
    table = common.name(source, "main", codec.TABLE)
    source.execute("BEGIN TRANSACTION")
    try:
        schema = source.execute(
            "SELECT column_name,data_type FROM information_schema.columns "
            "WHERE table_catalog=current_database() AND table_schema='main' AND table_name=? "
            "ORDER BY ordinal_position LIMIT 8",
            [codec.TABLE],
        ).fetchall()
        objects = source.execute(
            "SELECT table_type FROM information_schema.tables WHERE table_catalog="
            "current_database() AND table_schema='main' AND table_name=?",
            [codec.TABLE],
        ).fetchall()
        if tuple(schema) != codec.SCHEMA or objects != [("BASE TABLE",)]:
            raise codec.Rejected("EXACT_LEGACY_IV_SCHEMA_REQUIRED")
        totals = source.execute(
            f"SELECT count(*),coalesce(sum(coalesce(octet_length(encode(underlying)),0)"
            f"+coalesce(octet_length(encode(source)),0)),0),"
            f"coalesce(max(greatest(octet_length(encode(underlying)),"
            f"octet_length(encode(source)))),0) FROM {table}"
        ).fetchone()
        if totals is None or not 1 <= totals[0] <= codec.MAX_ROWS:
            raise codec.Rejected("WHOLE_TABLE_ROW_BOUND")
        if totals[1] > codec.MAX_BYTES or totals[2] > codec.MAX_CELL:
            raise codec.Rejected("TEXT_TRANSFER_BOUND")
        rows = source.execute(
            f"SELECT ts,CASE WHEN octet_length(encode(underlying))<=? THEN underlying END,"
            f"expiry,iv,spot,CASE WHEN octet_length(encode(source))<=? THEN source END "
            f"FROM {table} LIMIT ?",
            [codec.MAX_CELL, codec.MAX_CELL, codec.MAX_ROWS + 1],
        ).fetchall()
        if len(rows) != totals[0]:
            raise codec.Rejected("WHOLE_TABLE_ROW_BOUND")
        encoded: list[list[Any]] = []
        for ts, underlying, expiry, iv, spot, stored_source in rows:
            if (
                not isinstance(ts, datetime)
                or type(underlying) is not str
                or type(expiry) is not date
                or type(iv) is not float
                or (spot is not None and type(spot) is not float)
                or type(stored_source) is not str
            ):
                raise codec.Rejected("EXACT_STORED_SQL_TYPES_REQUIRED")
            encoded.append(
                [
                    common._clock(ts),
                    underlying,
                    expiry.isoformat(),
                    iv.hex(),
                    None if spot is None else spot.hex(),
                    stored_source,
                ]
            )
        snapshot = codec.make_snapshot(source_label, encoded)
        source.execute("COMMIT")
        return snapshot
    except BaseException:
        source.execute("ROLLBACK")
        raise


def preserve_underlying_iv(
    source: Any,
    bronze: Any,
    *,
    source_label: str,
    expected_snapshot_id: str,
    imported_at: datetime,
    actor_id: str,
    code_revision: str,
) -> dict[str, Any]:
    scope = scope_id(source_label)
    if (
        not codec.pin(expected_snapshot_id)
        or not common._actor(actor_id)
        or not common._revision(code_revision)
    ):
        raise codec.Rejected("REVIEWED_REQUEST_REQUIRED")
    common._clock(imported_at)
    common._separate(source, bronze)
    paths = bronze.execute(
        "SELECT path FROM duckdb_databases() WHERE database_name=current_database()"
    ).fetchall()
    if len(paths) != 1 or not paths[0][0]:
        raise codec.Rejected("FILE_BACKED_BRONZE_REQUIRED")
    common._readonly(source)
    store = BronzeEventStore(bronze)
    store.verify_target()
    for table, field, value in (
        (common.name(bronze, "medallion_audit", "jobs"), "scope_ref", "sha256:" + scope),
        (store.object_name("event_variants"), "capture_session_id", scope),
        (store.object_name("ingest_batches"), "batch_key", scope),
        (store.object_name("input_artifacts"), "artifact_hash", expected_snapshot_id),
    ):
        if bronze.execute(f'SELECT 1 FROM {table} WHERE "{field}"=? LIMIT 1', [value]).fetchone():
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
        first = capture_underlying_iv(source, source_label=source_label)
        if first.snapshot_id != expected_snapshot_id:
            raise codec.Rejected("REVIEWED_SOURCE_CHANGED")
        if capture_underlying_iv(source, source_label=source_label) != first:
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
    fingerprint, _raw = read_recording_bytes(
        bronze,
        source_label=source_label,
        snapshot_id=expected_snapshot_id,
        capture_event_id=event.capture_event_id,
        envelope_hash=event.envelope_hash,
    )
    return dict(
        source_label=source_label,
        snapshot_id=expected_snapshot_id,
        capture_event_id=event.capture_event_id,
        envelope_hash=event.envelope_hash,
        recording_fingerprint=fingerprint,
        row_count=first.row_count,
        job_id=job,
        decision_eligibility_asserted=False,
    )


def read_recording_bytes(
    bronze: Any, *, source_label: str, snapshot_id: str, capture_event_id: str, envelope_hash: str
) -> tuple[str, bytes]:
    """Original-recording verifier; public pinned readers additionally require readonly/pin."""
    if not all(codec.pin(p) for p in (snapshot_id, capture_event_id, envelope_hash)):
        raise codec.Rejected("EXACT_BRONZE_PINS_REQUIRED")
    scope = scope_id(source_label)
    store = BronzeEventStore(bronze)
    store.verify_target()
    variants = store.object_name("event_variants")
    batches = store.object_name("ingest_batches")
    artifacts = store.object_name("input_artifacts")
    jobs = common.name(bronze, "medallion_audit", "jobs")
    events = common.name(bronze, "medallion_audit", "job_events")
    bronze.execute("BEGIN TRANSACTION")
    try:
        rows = bronze.execute(
            f"SELECT CASE WHEN length(capture_event_id)<=64 THEN capture_event_id END,"
            f"CASE WHEN length(envelope_hash)<=64 THEN envelope_hash END,"
            f"CASE WHEN length(source)<=128 THEN source END,"
            f"CASE WHEN length(capture_session_id)<=64 THEN capture_session_id END,"
            f"CASE WHEN length(source_record_id)<=128 THEN source_record_id END,"
            f"received_at,recorded_at,exchange_ts,"
            f"CASE WHEN octet_length(payload)<=? THEN payload END,"
            f"CASE WHEN length(payload_hash)<=64 THEN payload_hash END,"
            f"CASE WHEN length(payload_format)<=128 THEN payload_format END,"
            f"CASE WHEN length(origin_kind)<=32 THEN origin_kind END,"
            f"CASE WHEN octet_length(encode(envelope_json))<=8192 THEN envelope_json END,"
            f"CASE WHEN length(first_batch_key)<=64 THEN first_batch_key END,"
            f"CASE WHEN length(first_job_id)<=128 THEN first_job_id END,ingest_sequence "
            f"FROM {variants} WHERE capture_event_id=? OR capture_session_id=? LIMIT 3",
            [codec.MAX_BYTES, capture_event_id, scope],
        ).fetchall()
        if (
            len(rows) != 1
            or rows[0][:2] != (capture_event_id, envelope_hash)
            or rows[0][8] is None
            or rows[0][12] is None
        ):
            raise codec.Rejected("EXACT_ORIGINAL_IV_VARIANT_REQUIRED")
        row = rows[0][2:]
        raw = bytes(row[6])
        doc = codec.replay_snapshot(raw, expected_snapshot_id=snapshot_id)
        event = BronzeEvent(
            SOURCE, scope, codec.TABLE, row[3], raw, codec.VERSION, "legacy_snapshot"
        )
        if (
            doc["source_label"] != source_label
            or row[:3] != (SOURCE, scope, codec.TABLE)
            or row[5] is not None
            or row[7:12]
            != (snapshot_id, codec.VERSION, "legacy_snapshot", event.envelope_json, scope)
            or event.capture_event_id != capture_event_id
            or event.envelope_hash != envelope_hash
        ):
            raise codec.Rejected("NATIVE_IV_ENVELOPE_MISMATCH")
        scoped = common._metadata(
            bronze,
            f"SELECT CASE WHEN length(job_id)<=128 THEN job_id END,"
            f"CASE WHEN parent_job_id IS NULL THEN NULL ELSE 'PRESENT' END,"
            f"CASE WHEN length(command_name)<=128 THEN command_name END,"
            f"CASE WHEN length(actor_id)<=128 THEN actor_id END,"
            f"CASE WHEN length(code_revision)<=40 THEN code_revision END,"
            f"CASE WHEN length(config_hash)<=64 THEN config_hash END,created_at "
            f"FROM {jobs} WHERE scope_ref=?",
            ["sha256:" + scope],
            1,
        )
        history = common._metadata(
            bronze,
            f"SELECT event_index,CASE WHEN length(state)<=32 THEN state END,recorded_at,"
            f"CASE WHEN reason_code IS NULL THEN NULL ELSE 'PRESENT' END "
            f"FROM {events} WHERE job_id=? ORDER BY event_index",
            [row[12]],
            3,
        )
        batch = common._metadata(
            bronze,
            f"SELECT CASE WHEN length(batch_fingerprint)<=64 THEN batch_fingerprint END,"
            f"CASE WHEN length(input_file_hash)<=64 THEN input_file_hash END,input_events,"
            f"inserted_variants,exact_retries,conflict_variants,last_sequence,"
            f"CASE WHEN length(job_id)<=128 THEN job_id END,committed_at "
            f"FROM {batches} WHERE batch_key=?",
            [scope],
            1,
        )
        artifact = bronze.execute(
            f"SELECT CASE WHEN octet_length(artifact_bytes)<=? THEN artifact_bytes END,"
            f"CASE WHEN length(first_job_id)<=128 THEN first_job_id END,recorded_at "
            f"FROM {artifacts} WHERE artifact_hash=? LIMIT 2",
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
        or not common._actor(scoped[0][3])
        or not common._revision(scoped[0][4])
        or scoped[0][5] != config
        or [(h[0], h[1], h[3]) for h in history]
        != [(1, "PLANNED", None), (2, "RUNNING", None), (3, "SUCCEEDED", None)]
    ):
        raise codec.Rejected("ORIGINAL_IV_AUDIT_NOT_VERIFIED")
    batch_fp = codec.sha(
        codec.canonical(
            dict(input_file_hash=snapshot_id, events=[(capture_event_id, envelope_hash)])
        )
    )
    if (
        len(batch) != 1
        or batch[0][:8] != (batch_fp, snapshot_id, 1, 1, 0, 0, row[13], row[12])
        or type(row[13]) is not int
        or row[13] <= 0
        or len(artifact) != 1
        or artifact[0][0] is None
        or bytes(artifact[0][0]) != raw
        or artifact[0][1] != row[12]
    ):
        raise codec.Rejected("ORIGINAL_IV_BATCH_NOT_VERIFIED")
    for at in [row[3], row[4], scoped[0][6], batch[0][8], artifact[0][2], *(h[2] for h in history)]:
        common._clock(at)
    metadata = [
        VERSION,
        capture_event_id,
        envelope_hash,
        list(row[:6]),
        codec.sha(raw),
        list(row[7:]),
        scoped,
        history,
        batch,
        list(artifact[0][1:]),
    ]
    return codec.sha(common._json(metadata)), raw


def read_underlying_iv_bronze(
    bronze: Any,
    *,
    source_label: str,
    snapshot_id: str,
    capture_event_id: str,
    envelope_hash: str,
    expected_recording_fingerprint: str,
) -> tuple[bytes, ...]:
    if not codec.pin(expected_recording_fingerprint):
        raise codec.Rejected("EXACT_RECORDING_PIN_REQUIRED")
    common._readonly(bronze)
    fingerprint, raw = read_recording_bytes(
        bronze,
        source_label=source_label,
        snapshot_id=snapshot_id,
        capture_event_id=capture_event_id,
        envelope_hash=envelope_hash,
    )
    if fingerprint != expected_recording_fingerprint:
        raise codec.Rejected("IV_RECORDING_FINGERPRINT_CHANGED")
    return codec.derive_records(
        raw, snapshot_id=snapshot_id, capture_event_id=capture_event_id, envelope_hash=envelope_hash
    )


def revalidate_underlying_iv_source(source: Any, bronze: Any, **pins: Any) -> tuple[bytes, ...]:
    common._separate(source, bronze)
    first = read_underlying_iv_bronze(bronze, **pins)
    for _ in range(2):
        if (
            capture_underlying_iv(source, source_label=pins["source_label"]).snapshot_id
            != pins["snapshot_id"]
        ):
            raise codec.Rejected("CURRENT_LEGACY_IV_SOURCE_CHANGED")
    second = read_underlying_iv_bronze(bronze, **pins)
    if first != second:
        raise codec.Rejected("IV_RECORDING_CHANGED_DURING_REVALIDATION")
    return second
