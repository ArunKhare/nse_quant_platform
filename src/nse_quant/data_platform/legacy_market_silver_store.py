"""Audited immutable Silver legacy sets from actual verified native Bronze snapshots."""

from __future__ import annotations

import json
import platform
import re
from dataclasses import asdict
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

from nse_quant.data_platform import legacy_market_silver as codec
from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.contracts import DatasetContract, Layer, WritePolicy

COMMAND = "normalize.legacy_market_silver@1"
TABLES = {
    ("silver", n)
    for n in (
        "legacy_schema_versions",
        "legacy_sets",
        "legacy_observations",
        "legacy_attempts",
    )
} | {
    ("medallion_audit", n)
    for n in (
        "schema_versions",
        "dataset_contracts",
        "jobs",
        "job_events",
    )
}
CONTRACT = DatasetContract(
    "silver.legacy_observations",
    "1",
    Layer.SILVER,
    WritePolicy.APPEND_REVISIONS,
    ("revision_id", "ordinal"),
    ("revision_id", "ordinal", "source_observation_id", "recorded_at", "record_bytes"),
    "native_legacy_market_silver",
)


def name(conn: Any, schema: str, table: str) -> str:
    row = conn.execute("SELECT current_database()").fetchone()
    if row is None:
        raise codec.SilverRejected("CATALOG_UNAVAILABLE")
    return ".".join('"' + str(x).replace('"', '""') + '"' for x in (row[0], schema, table))


def _owned(conn: Any, *, complete: bool) -> None:
    paths = conn.execute(
        "SELECT path FROM duckdb_databases() WHERE database_name=current_database()"
    ).fetchall()
    if len(paths) != 1 or not paths[0][0]:
        raise codec.SilverRejected("FILE_BACKED_SILVER_REQUIRED")
    rows = conn.execute(
        "SELECT table_schema,table_name,table_type FROM information_schema.tables "
        "WHERE table_catalog=current_database() ORDER BY table_schema,table_name LIMIT 9"
    ).fetchall()
    known = {(s, t) for s, t, _kind in rows}
    if (
        known - TABLES
        or any(k != "BASE TABLE" for _, _, k in rows)
        or (complete and known != TABLES)
    ):
        raise codec.SilverRejected("DEDICATED_LEGACY_SILVER_REQUIRED")


def _paths(conn: Any) -> set[Path]:
    return {Path(r[2]).resolve() for r in conn.execute("PRAGMA database_list").fetchall() if r[2]}


def _separate(bronze: Any, target: Any) -> None:
    if bronze is target or any(
        a == b or a.samefile(b) for a in _paths(bronze) for b in _paths(target)
    ):
        raise codec.SilverRejected("SEPARATE_SILVER_DATABASE_REQUIRED")


def _definition() -> bytes:
    return codec.canonical([codec.DEFINITION, CONTRACT.canonical_json()])


def initialize_legacy_silver(target: Any) -> None:
    """Explicit dedicated empty target only. Never adopts partial or existing data."""
    _owned(target, complete=False)
    if target.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_catalog=current_database() LIMIT 1"
    ).fetchone():
        raise codec.SilverRejected("EMPTY_SILVER_INITIALIZATION_REQUIRED")
    AuditLedger(target).initialize()
    schema = name(target, "silver", "legacy_schema_versions")
    sets = name(target, "silver", "legacy_sets")
    records = name(target, "silver", "legacy_observations")
    attempts = name(target, "silver", "legacy_attempts")
    target.execute("BEGIN TRANSACTION")
    try:
        target.execute(f"CREATE SCHEMA {schema.rsplit('.', 1)[0]}")
        target.execute(
            f"CREATE TABLE {schema} (version INTEGER PRIMARY KEY,definition BLOB NOT NULL)"
        )
        target.execute(f"INSERT INTO {schema} VALUES (1,?)", [_definition()])
        target.execute(f"""CREATE TABLE {sets} (
            revision_id VARCHAR PRIMARY KEY,scope_id VARCHAR UNIQUE NOT NULL,
            source_pins BLOB NOT NULL,source_context BLOB NOT NULL,
            observation_count INTEGER NOT NULL,first_job_id VARCHAR NOT NULL,
            recorded_at TIMESTAMPTZ NOT NULL)""")
        target.execute(f"""CREATE TABLE {records} (
            revision_id VARCHAR NOT NULL,ordinal INTEGER NOT NULL,record_id VARCHAR NOT NULL,
            source_table VARCHAR NOT NULL,instrument_token BIGINT NOT NULL,
            stored_ts TIMESTAMPTZ NOT NULL,volume BIGINT,oi BIGINT,record_bytes BLOB NOT NULL,
            source_observation_id VARCHAR NOT NULL,recorded_at TIMESTAMPTZ NOT NULL,
            PRIMARY KEY(revision_id,ordinal))""")
        target.execute(f"""CREATE TABLE {attempts} (
            job_id VARCHAR PRIMARY KEY,scope_id VARCHAR NOT NULL,revision_id VARCHAR NOT NULL)""")
        target.execute("COMMIT")
    except BaseException:
        target.execute("ROLLBACK")
        raise
    AuditLedger(target).register_contract(CONTRACT)


def _schema(conn: Any) -> None:
    _owned(conn, complete=True)
    table = name(conn, "silver", "legacy_schema_versions")
    if conn.execute(
        f"SELECT version,CASE WHEN octet_length(definition)<=32768 THEN definition END "
        f"FROM {table} LIMIT 2"
    ).fetchall() != [(1, _definition())]:
        raise codec.SilverRejected("SILVER_DEFINITION_DRIFT")
    contracts = name(conn, "medallion_audit", "dataset_contracts")
    if conn.execute(
        f"SELECT fingerprint,CASE WHEN length(contract_json)<=32768 THEN contract_json END "
        f"FROM {contracts} WHERE dataset_name=? AND contract_version='1'",
        [CONTRACT.name],
    ).fetchall() != [(CONTRACT.fingerprint, CONTRACT.canonical_json())]:
        raise codec.SilverRejected("SILVER_DATASET_CONTRACT_DRIFT")
    audit = name(conn, "medallion_audit", "schema_versions")
    if conn.execute(f"SELECT version FROM {audit} LIMIT 2").fetchall() != [(1,)]:
        raise codec.SilverRejected("AUDIT_SCHEMA_DRIFT")


def _json_bytes(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=codec._clock
    ).encode()


def _bounded_rows(conn: Any, sql: str, args: list[object], maximum: int) -> list[Any]:
    rows = conn.execute(sql, args).fetchmany(maximum + 1)
    if len(rows) > maximum:
        raise codec.SilverRejected("SOURCE_METADATA_COVERAGE_BOUND")
    for row in rows:
        if any(isinstance(x, str) and len(x.encode()) > 8192 for x in row):
            raise codec.SilverRejected("SOURCE_METADATA_FIELD_BOUND")
    return rows


def observe_legacy_bronze(bronze: Any, *, pins: codec.LegacyBronzePins) -> bytes:
    """Actual native reads bracket complete bounded original recording metadata.

    Sequential observations, not an atomic cross-resource snapshot. Returned bytes
    are reviewable observation context, not independently authenticated provenance.
    """
    from nse_quant.data_platform import legacy_market_snapshot as source

    if type(pins) is not codec.LegacyBronzePins or source.VERSION != codec.SOURCE_VERSION:
        raise codec.SilverRejected("UNSUPPORTED_LEGACY_SOURCE_CONTRACT")
    checked = codec.LegacyBronzePins(**asdict(pins))
    args = dict(
        capture_event_id=checked.capture_event_id,
        envelope_hash=checked.envelope_hash,
        expected_snapshot_id=checked.snapshot_id,
    )
    first = source.read_preserved_legacy_snapshot(bronze, **args)
    codec.derive_records(first, pins=checked)
    event = name(bronze, "bronze", "event_variants")
    batches = name(bronze, "bronze", "ingest_batches")
    artifacts = name(bronze, "bronze", "input_artifacts")
    jobs = name(bronze, "medallion_audit", "jobs")
    events = name(bronze, "medallion_audit", "job_events")
    bronze.execute("BEGIN TRANSACTION")
    try:
        variants = _bounded_rows(
            bronze,
            f"SELECT capture_event_id,envelope_hash,ingest_sequence,source,capture_session_id,"
            f"source_record_id,received_at,recorded_at,exchange_ts,payload_hash,payload_format,"
            f"origin_kind,envelope_json,first_batch_key,first_job_id FROM {event} "
            "WHERE capture_event_id=?",
            [checked.capture_event_id],
            1,
        )
        if len(variants) != 1:
            raise codec.SilverRejected("ORIGINAL_BRONZE_VARIANT_MISSING")
        job_id = variants[0][-1]
        original = _bounded_rows(bronze, f"SELECT * FROM {jobs} WHERE job_id=?", [job_id], 1)
        if len(original) != 1:
            raise codec.SilverRejected("ORIGINAL_BRONZE_JOB_MISSING")
        scope = original[0][4]
        scoped = _bounded_rows(
            bronze, f"SELECT * FROM {jobs} WHERE scope_ref=? ORDER BY job_id", [scope], 1
        )
        history = _bounded_rows(
            bronze, f"SELECT * FROM {events} WHERE job_id=? ORDER BY event_index", [job_id], 3
        )
        batch = _bounded_rows(
            bronze, f"SELECT * FROM {batches} WHERE batch_key=?", [variants[0][-2]], 1
        )
        artifact = _bounded_rows(
            bronze,
            f"SELECT artifact_hash,recorded_at,first_job_id,octet_length(artifact_bytes) "
            f"FROM {artifacts} WHERE artifact_hash=?",
            [checked.snapshot_id],
            1,
        )
        bronze.execute("COMMIT")
    except BaseException:
        bronze.execute("ROLLBACK")
        raise
    second = source.read_preserved_legacy_snapshot(bronze, **args)
    if source.canonical(first) != source.canonical(second):
        raise codec.SilverRejected("LEGACY_BRONZE_CONTEXT_DRIFT")
    raw = _json_bytes(
        dict(
            version=codec.VERSION,
            pins=asdict(checked),
            observations=first,
            recording=dict(
                variants=variants, jobs=scoped, history=history, batch=batch, artifact=artifact
            ),
            runtime=dict(python=platform.python_version(), duckdb=version("duckdb")),
        )
    )
    if len(raw) > codec.MAX_SET_BYTES:
        raise codec.SilverRejected("NATIVE_SOURCE_CONTEXT_BYTE_BOUND")
    return raw


def _derive(context: bytes, pins: codec.LegacyBronzePins) -> tuple[bytes, ...]:
    if type(context) is not bytes or not 0 < len(context) <= codec.MAX_SET_BYTES:
        raise codec.SilverRejected("NATIVE_SOURCE_CONTEXT_BYTE_BOUND")
    try:
        doc = json.loads(context)
        if (
            codec.canonical(doc) != context
            or doc["version"] != codec.VERSION
            or doc["pins"] != asdict(pins)
        ):
            raise codec.SilverRejected("SILVER_SOURCE_CONTEXT_CONTRACT")
        return codec.derive_records(tuple(doc["observations"]), pins=pins)
    except codec.SilverRejected:
        raise
    except (ValueError, KeyError, TypeError, RecursionError):
        raise codec.SilverRejected("SILVER_SOURCE_CONTEXT_MALFORMED") from None


def _revision(
    pins: codec.LegacyBronzePins,
    context: bytes,
    records: tuple[bytes, ...],
) -> str:
    return codec.sha(
        codec.canonical(
            [
                codec.definition_sha256(),
                asdict(pins),
                codec.sha(context),
                [codec.sha(r) for r in records],
            ]
        )
    )


def persist_legacy_silver(
    bronze: Any,
    target: Any,
    *,
    pins: codec.LegacyBronzePins,
    expected_source_context_sha256: str,
    actor_id: str,
    code_revision: str,
) -> dict[str, Any]:
    """Native verified-source -> audited first-write set and every observation atomically."""
    if type(pins) is not codec.LegacyBronzePins:
        raise codec.SilverRejected("TYPED_SOURCE_PINS_REQUIRED")
    pins = codec.LegacyBronzePins(**asdict(pins))
    if (
        not codec.pin(expected_source_context_sha256)
        or type(actor_id) is not str
        or not 1 <= len(actor_id) <= 128
        or actor_id != actor_id.strip()
        or any(ord(c) < 32 for c in actor_id)
        or type(code_revision) is not str
        or re.fullmatch(r"[a-f0-9]{40}", code_revision) is None
    ):
        raise codec.SilverRejected("EXACT_REVIEWED_SILVER_REQUEST_REQUIRED")
    _separate(bronze, target)
    _schema(target)
    sets = name(target, "silver", "legacy_sets")
    records_table = name(target, "silver", "legacy_observations")
    attempts = name(target, "silver", "legacy_attempts")
    jobs = name(target, "medallion_audit", "jobs")
    if (
        target.execute(f"SELECT 1 FROM {sets} WHERE scope_id=? LIMIT 1", [pins.scope_id]).fetchone()
        or target.execute(
            f"SELECT 1 FROM {jobs} WHERE scope_ref=? LIMIT 1", ["sha256:" + pins.scope_id]
        ).fetchone()
        or target.execute(
            f"SELECT 1 FROM {attempts} WHERE scope_id=? LIMIT 1", [pins.scope_id]
        ).fetchone()
    ):
        raise codec.SilverRejected("SILVER_FIRST_WRITE_ORIGINAL_OBLIGATION")
    if target.execute(
        f"SELECT 1 FROM {records_table} WHERE source_observation_id=? LIMIT 1",
        [pins.capture_event_id],
    ).fetchone():
        raise codec.SilverRejected("SILVER_ORPHAN_OR_PRIOR_EVENT_ROWS")
    job = AuditLedger(target).plan_job(
        command_name=COMMAND,
        actor_id=actor_id,
        code_revision=code_revision,
        scope_ref="sha256:" + pins.scope_id,
        config_hash=codec.sha(
            codec.canonical([_definition().hex(), expected_source_context_sha256])
        ),
    )
    with AuditLedger(target).execution(job):
        first = observe_legacy_bronze(bronze, pins=pins)
        if codec.sha(first) != expected_source_context_sha256:
            raise codec.SilverRejected("REVIEWED_BRONZE_CONTEXT_CHANGED")
        records = _derive(first, pins)
        second = observe_legacy_bronze(bronze, pins=pins)
        if first != second:
            raise codec.SilverRejected("BRONZE_FULL_CONTEXT_DRIFT")
        revision = _revision(pins, first, records)
        recorded_at = datetime.now(UTC)
        target.execute("BEGIN TRANSACTION")
        try:
            target.execute(
                f"INSERT INTO {sets} VALUES (?,?,?,?,?,?,?)",
                [
                    revision,
                    pins.scope_id,
                    codec.canonical(asdict(pins)),
                    first,
                    len(records),
                    job,
                    recorded_at,
                ],
            )
            for raw in records:
                rid, ordinal, table, token, ts, volume, oi, _raw = codec.record_values(raw)
                target.execute(
                    f"INSERT INTO {records_table} VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    [
                        revision,
                        ordinal,
                        rid,
                        table,
                        token,
                        ts,
                        volume,
                        oi,
                        raw,
                        pins.capture_event_id,
                        recorded_at,
                    ],
                )
            target.execute(f"INSERT INTO {attempts} VALUES (?,?,?)", [job, pins.scope_id, revision])
            target.execute("COMMIT")
        except BaseException:
            target.execute("ROLLBACK")
            raise
    fingerprint, _rows = _recording(target, revision)
    return dict(
        revision_id=revision,
        recording_fingerprint=fingerprint,
        row_count=len(records),
        job_id=job,
        decision_eligibility_asserted=False,
    )


def _recording(target: Any, revision: str) -> tuple[str, tuple[bytes, ...]]:
    _schema(target)
    if not codec.pin(revision):
        raise codec.SilverRejected("EXACT_SILVER_REVISION_REQUIRED")
    sets = name(target, "silver", "legacy_sets")
    records = name(target, "silver", "legacy_observations")
    attempts = name(target, "silver", "legacy_attempts")
    jobs = name(target, "medallion_audit", "jobs")
    events = name(target, "medallion_audit", "job_events")
    target.execute("BEGIN TRANSACTION")
    try:
        row = target.execute(
            f"SELECT scope_id,CASE WHEN octet_length(source_pins)<=512 THEN source_pins END,"
            f"CASE WHEN octet_length(source_context)<=? THEN source_context END,"
            f"observation_count,first_job_id,recorded_at FROM {sets} WHERE revision_id=?",
            [codec.MAX_SET_BYTES, revision],
        ).fetchone()
        if row is None or row[1] is None or row[2] is None:
            raise codec.SilverRejected("SILVER_SET_MISSING_OR_UNBOUNDED")
        totals = target.execute(
            f"SELECT count(*),coalesce(sum(octet_length(record_bytes)),0) "
            f"FROM {records} WHERE revision_id=?",
            [revision],
        ).fetchone()
        if (
            totals is None
            or not 1 <= totals[0] <= codec.MAX_ROWS
            or totals[1] > codec.MAX_SET_BYTES
        ):
            raise codec.SilverRejected("SILVER_ROW_COVERAGE_OR_BYTE_BOUND")
        stored = target.execute(
            f"SELECT ordinal,record_id,source_table,instrument_token,stored_ts,volume,oi,"
            f"CASE WHEN octet_length(record_bytes)<=? THEN record_bytes END,"
            f"source_observation_id,recorded_at FROM {records} WHERE revision_id=? "
            "ORDER BY ordinal LIMIT ?",
            [codec.MAX_ROW_BYTES, revision, codec.MAX_ROWS + 1],
        ).fetchall()
        links = target.execute(
            f"SELECT * FROM {attempts} WHERE scope_id=? OR revision_id=? ORDER BY job_id LIMIT 3",
            [row[0], revision],
        ).fetchall()
        scoped = _bounded_rows(
            target,
            f"SELECT * FROM {jobs} WHERE scope_ref=? ORDER BY job_id",
            ["sha256:" + row[0]],
            1,
        )
        history = _bounded_rows(
            target, f"SELECT * FROM {events} WHERE job_id=? ORDER BY event_index", [row[4]], 3
        )
        target.execute("COMMIT")
    except BaseException:
        target.execute("ROLLBACK")
        raise
    pins = codec.LegacyBronzePins(**json.loads(bytes(row[1])))
    context = bytes(row[2])
    expected = _derive(context, pins)
    if (
        pins.scope_id != row[0]
        or codec.canonical(asdict(pins)) != bytes(row[1])
        or _revision(pins, context, expected) != revision
        or row[3] != len(expected)
        or len(stored) != len(expected)
        or links != [(row[4], row[0], revision)]
    ):
        raise codec.SilverRejected("SILVER_SET_OR_COVERAGE_MISMATCH")
    for got, raw in zip(stored, expected, strict=True):
        rid, ordinal, table, token, ts, volume, oi, _raw = codec.record_values(raw)
        if (
            got[:7] != (ordinal, rid, table, token, ts, volume, oi)
            or got[7] is None
            or bytes(got[7]) != raw
            or got[8:] != (pins.capture_event_id, row[5])
        ):
            raise codec.SilverRejected("COMPLETE_SILVER_ROW_RECOMPUTATION_MISMATCH")
    expected_config = codec.sha(codec.canonical([_definition().hex(), codec.sha(context)]))
    if (
        len(scoped) != 1
        or scoped[0][0] != row[4]
        or scoped[0][1] is not None
        or scoped[0][2] != COMMAND
        or not scoped[0][3]
        or re.fullmatch(r"[a-f0-9]{40}", scoped[0][5]) is None
        or scoped[0][6] != expected_config
        or len(history) != 3
        or [(h[1], h[2], h[4]) for h in history]
        != [(1, "PLANNED", None), (2, "RUNNING", None), (3, "SUCCEEDED", None)]
    ):
        raise codec.SilverRejected("ORIGINAL_SILVER_AUDIT_NOT_VERIFIED")
    codec._clock(row[5])
    codec._clock(scoped[0][7])
    for h in history:
        codec._clock(h[3])
    fingerprint = codec.sha(
        _json_bytes(
            [
                codec.VERSION,
                revision,
                list(row[:1]),
                bytes(row[1]).hex(),
                codec.sha(context),
                list(row[3:]),
                [[*r[:7], codec.sha(bytes(r[7])), *r[8:]] for r in stored],
                links,
                scoped,
                history,
            ]
        )
    )
    return fingerprint, expected


def read_legacy_silver(
    source: Any,
    *,
    revision_id: str,
    expected_recording_fingerprint: str,
) -> tuple[bytes, ...]:
    """Original recording verification and full row replay, no current-Bronze assertion."""
    if not codec.pin(expected_recording_fingerprint):
        raise codec.SilverRejected("EXACT_SILVER_RECORDING_PIN_REQUIRED")
    if source.execute(
        "SELECT readonly FROM duckdb_databases() WHERE database_name=current_database()"
    ).fetchall() != [(True,)]:
        raise codec.SilverRejected("READONLY_SILVER_SOURCE_REQUIRED")
    fingerprint, records = _recording(source, revision_id)
    if fingerprint != expected_recording_fingerprint:
        raise codec.SilverRejected("SILVER_RECORDING_FINGERPRINT_CHANGED")
    return records


def revalidate_legacy_silver(
    bronze: Any,
    silver: Any,
    *,
    revision_id: str,
    expected_recording_fingerprint: str,
) -> tuple[bytes, ...]:
    """Original recording verification PLUS actual repeated native Bronze revalidation."""
    _separate(bronze, silver)
    first = read_legacy_silver(
        silver,
        revision_id=revision_id,
        expected_recording_fingerprint=expected_recording_fingerprint,
    )
    record = json.loads(first[0])
    pins = codec.LegacyBronzePins(**record["source_pins"])
    sets = name(silver, "silver", "legacy_sets")
    row = silver.execute(
        f"SELECT CASE WHEN octet_length(source_context)<=? THEN source_context END "
        f"FROM {sets} WHERE revision_id=?",
        [codec.MAX_SET_BYTES, revision_id],
    ).fetchone()
    if row is None or row[0] is None:
        raise codec.SilverRejected("SILVER_SET_MISSING_OR_UNBOUNDED")
    frozen = bytes(row[0])
    if (
        observe_legacy_bronze(bronze, pins=pins) != frozen
        or observe_legacy_bronze(bronze, pins=pins) != frozen
    ):
        raise codec.SilverRejected("ORIGINAL_BRONZE_CONTEXT_NO_LONGER_MATCHES")
    second = read_legacy_silver(
        silver,
        revision_id=revision_id,
        expected_recording_fingerprint=expected_recording_fingerprint,
    )
    if first != second:
        raise codec.SilverRejected("SILVER_CHANGED_DURING_REVALIDATION")
    return second
