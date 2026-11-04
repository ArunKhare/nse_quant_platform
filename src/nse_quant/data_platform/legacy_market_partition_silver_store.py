"""Audited first-write partition Silver; native readers, no successful DTO import."""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from nse_quant.data_platform import legacy_market_partition_silver as codec
from nse_quant.data_platform import legacy_market_partitions_store as bronze_source
from nse_quant.data_platform import legacy_market_silver_store as foundation
from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.contracts import DatasetContract, Layer, WritePolicy

COMMAND = "normalize.legacy_market_partition_silver@1"
CONTRACT = DatasetContract(
    "silver.partition_legacy_observations",
    "1",
    Layer.SILVER,
    WritePolicy.APPEND_REVISIONS,
    ("revision_id", "ordinal"),
    ("revision_id", "ordinal", "source_observation_id", "recorded_at", "record_bytes"),
    "native_legacy_market_partition_silver",
)
TABLES = {
    ("silver", n)
    for n in (
        "partition_legacy_versions",
        "partition_legacy_sets",
        "partition_legacy_observations",
        "partition_legacy_attempts",
    )
} | {("medallion_audit", n) for n in ("schema_versions", "dataset_contracts", "jobs", "job_events")}
name = foundation.name
Rejected = codec.PartitionSilverRejected


def _definition() -> bytes:
    return codec.canonical([codec.DEFINITION, CONTRACT.canonical_json()])


def _owned(conn: Any, *, complete: bool) -> None:
    paths = conn.execute(
        "SELECT path FROM duckdb_databases() WHERE database_name=current_database()"
    ).fetchall()
    rows = conn.execute(
        "SELECT table_schema,table_name,table_type FROM information_schema.tables "
        "WHERE table_catalog=current_database() ORDER BY table_schema,table_name LIMIT 9"
    ).fetchall()
    known = {(s, t) for s, t, _kind in rows}
    if len(paths) != 1 or not paths[0][0]:
        raise Rejected("FILE_BACKED_PARTITION_SILVER_REQUIRED")
    if known - TABLES or any(k != "BASE TABLE" for _, _, k in rows):
        raise Rejected("DEDICATED_PARTITION_SILVER_REQUIRED")
    if complete and known != TABLES:
        raise Rejected("COMPLETE_PARTITION_SILVER_SCHEMA_REQUIRED")


def initialize_partition_silver(target: Any) -> None:
    """Explicit initialization of a dedicated empty file, never adoption."""
    _owned(target, complete=False)
    if target.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_catalog=current_database() LIMIT 1"
    ).fetchone():
        raise Rejected("EMPTY_PARTITION_SILVER_INITIALIZATION_REQUIRED")
    AuditLedger(target).initialize()
    versions = name(target, "silver", "partition_legacy_versions")
    sets = name(target, "silver", "partition_legacy_sets")
    records = name(target, "silver", "partition_legacy_observations")
    attempts = name(target, "silver", "partition_legacy_attempts")
    target.execute("BEGIN TRANSACTION")
    try:
        target.execute(f"CREATE SCHEMA {versions.rsplit('.', 1)[0]}")
        target.execute(f"CREATE TABLE {versions} (version INTEGER PRIMARY KEY,definition BLOB)")
        target.execute(f"INSERT INTO {versions} VALUES (1,?)", [_definition()])
        target.execute(f"""CREATE TABLE {sets} (
            revision_id VARCHAR PRIMARY KEY,scope_id VARCHAR UNIQUE NOT NULL,
            capture_id VARCHAR UNIQUE NOT NULL,source_pins BLOB NOT NULL,
            source_artifact BLOB NOT NULL,row_count INTEGER NOT NULL,
            first_job_id VARCHAR NOT NULL,recorded_at TIMESTAMPTZ NOT NULL)""")
        target.execute(f"""CREATE TABLE {records} (
            revision_id VARCHAR NOT NULL,ordinal INTEGER NOT NULL,
            partition_index INTEGER NOT NULL,partition_ordinal INTEGER NOT NULL,
            partition_payload_sha256 VARCHAR NOT NULL,record_id VARCHAR NOT NULL,
            source_table VARCHAR NOT NULL,instrument_token BIGINT NOT NULL,
            stored_ts TIMESTAMPTZ NOT NULL,volume BIGINT,oi BIGINT,
            record_bytes BLOB NOT NULL,source_observation_id VARCHAR NOT NULL,
            capture_id VARCHAR NOT NULL,recorded_at TIMESTAMPTZ NOT NULL,
            PRIMARY KEY(revision_id,ordinal),
            UNIQUE(revision_id,partition_index,partition_ordinal))""")
        target.execute(f"""CREATE TABLE {attempts} (
            job_id VARCHAR PRIMARY KEY,scope_id VARCHAR NOT NULL,revision_id VARCHAR NOT NULL)""")
        target.execute("COMMIT")
    except BaseException:
        target.execute("ROLLBACK")
        raise
    AuditLedger(target).register_contract(CONTRACT)


def _schema(conn: Any) -> None:
    _owned(conn, complete=True)
    versions = name(conn, "silver", "partition_legacy_versions")
    contracts = name(conn, "medallion_audit", "dataset_contracts")
    audit = name(conn, "medallion_audit", "schema_versions")
    if conn.execute(
        f"SELECT version,CASE WHEN octet_length(definition)<=32768 THEN definition END "
        f"FROM {versions} LIMIT 2"
    ).fetchall() != [(1, _definition())]:
        raise Rejected("PARTITION_SILVER_DEFINITION_DRIFT")
    if conn.execute(
        f"SELECT fingerprint,CASE WHEN length(contract_json)<=32768 THEN contract_json END "
        f"FROM {contracts} WHERE dataset_name=? AND contract_version='1'",
        [CONTRACT.name],
    ).fetchall() != [(CONTRACT.fingerprint, CONTRACT.canonical_json())]:
        raise Rejected("PARTITION_SILVER_CONTRACT_DRIFT")
    if conn.execute(f"SELECT version FROM {audit} LIMIT 2").fetchall() != [(1,)]:
        raise Rejected("PARTITION_SILVER_AUDIT_SCHEMA_DRIFT")


def _observe(bronze: Any, pins: codec.PartitionBronzePins) -> bytes:
    # A caller cannot supply a successful recording object to this boundary.
    first = bronze_source.read_partitioned_legacy_recording(bronze, **pins.reader_arguments())
    codec.derive_partition_records(first.capture.artifact, pins=pins)
    second = bronze_source.read_partitioned_legacy_recording(bronze, **pins.reader_arguments())
    if first != second:
        raise Rejected("PARTITION_BRONZE_RECORDING_DRIFT")
    return first.capture.artifact


def _config(pins: codec.PartitionBronzePins) -> str:
    return codec.sha(codec.canonical([_definition().hex(), asdict(pins)]))


def _revision(pins: codec.PartitionBronzePins, artifact: bytes, rows: tuple[bytes, ...]) -> str:
    return codec.sha(
        codec.canonical([_config(pins), codec.sha(artifact), [codec.sha(raw) for raw in rows]])
    )


def persist_partition_silver(
    bronze: Any,
    target: Any,
    *,
    pins: codec.PartitionBronzePins,
    actor_id: str,
    code_revision: str,
) -> dict[str, Any]:
    """Actual pinned partition Bronze -> atomic complete Silver domain, then final audit."""
    pins = codec.checked_pins(pins)
    if (
        type(actor_id) is not str
        or not 1 <= len(actor_id) <= 128
        or actor_id != actor_id.strip()
        or any(ord(c) < 32 for c in actor_id)
        or type(code_revision) is not str
        or re.fullmatch(r"[a-f0-9]{40}", code_revision) is None
    ):
        raise Rejected("EXPLICIT_PARTITION_SILVER_EXECUTION_IDENTIFIERS_REQUIRED")
    foundation._separate(bronze, target)
    _schema(target)
    sets = name(target, "silver", "partition_legacy_sets")
    records = name(target, "silver", "partition_legacy_observations")
    attempts = name(target, "silver", "partition_legacy_attempts")
    jobs = name(target, "medallion_audit", "jobs")
    if (
        target.execute(
            f"SELECT 1 FROM {sets} WHERE scope_id=? OR capture_id=? LIMIT 1",
            [pins.scope_id, pins.capture_id],
        ).fetchone()
        or target.execute(
            f"SELECT 1 FROM {attempts} WHERE scope_id=? LIMIT 1", [pins.scope_id]
        ).fetchone()
        or target.execute(
            f"SELECT 1 FROM {jobs} WHERE scope_ref=? LIMIT 1", ["sha256:" + pins.scope_id]
        ).fetchone()
    ):
        raise Rejected("PARTITION_SILVER_FIRST_WRITE_ORIGINAL_OBLIGATION")
    if target.execute(
        f"SELECT 1 FROM {records} WHERE capture_id=? LIMIT 1", [pins.capture_id]
    ).fetchone():
        raise Rejected("PARTITION_SILVER_ORPHAN_CAPTURE_ROWS")
    job = AuditLedger(target).plan_job(
        command_name=COMMAND,
        actor_id=actor_id,
        scope_ref="sha256:" + pins.scope_id,
        code_revision=code_revision,
        config_hash=_config(pins),
    )
    with AuditLedger(target).execution(job):
        artifact = _observe(bronze, pins)
        rows = codec.derive_partition_records(artifact, pins=pins)
        if _observe(bronze, pins) != artifact:
            raise Rejected("PARTITION_BRONZE_RECORDING_DRIFT")
        revision = _revision(pins, artifact, rows)
        at = datetime.now(UTC)
        target.execute("BEGIN TRANSACTION")
        try:
            target.execute(
                f"INSERT INTO {sets} VALUES (?,?,?,?,?,?,?,?)",
                [
                    revision,
                    pins.scope_id,
                    pins.capture_id,
                    codec.canonical(asdict(pins)),
                    artifact,
                    len(rows),
                    job,
                    at,
                ],
            )
            for raw in rows:
                target.execute(
                    f"INSERT INTO {records} VALUES ({','.join('?' for _ in range(15))})",
                    [revision, *codec.record_values(raw), at],
                )
            target.execute(f"INSERT INTO {attempts} VALUES (?,?,?)", [job, pins.scope_id, revision])
            target.execute("COMMIT")
        except BaseException:
            target.execute("ROLLBACK")
            raise
    fingerprint, _rows, _pins, _artifact = _recording(target, revision)
    return dict(
        revision_id=revision,
        recording_fingerprint=fingerprint,
        row_count=len(rows),
        job_id=job,
        decision_eligibility_asserted=False,
    )


def _recording(
    conn: Any,
    revision: str,
) -> tuple[str, tuple[bytes, ...], codec.PartitionBronzePins, bytes]:
    _schema(conn)
    if not codec.pin(revision):
        raise Rejected("EXACT_PARTITION_SILVER_REVISION_REQUIRED")
    sets = name(conn, "silver", "partition_legacy_sets")
    records = name(conn, "silver", "partition_legacy_observations")
    attempts = name(conn, "silver", "partition_legacy_attempts")
    jobs = name(conn, "medallion_audit", "jobs")
    events = name(conn, "medallion_audit", "job_events")
    conn.execute("BEGIN TRANSACTION")
    try:
        row = conn.execute(
            f"SELECT scope_id,capture_id,CASE WHEN octet_length(source_pins)<=1024 "
            f"THEN source_pins END,CASE WHEN octet_length(source_artifact)<=? "
            f"THEN source_artifact END,row_count,first_job_id,recorded_at "
            f"FROM {sets} WHERE revision_id=?",
            [codec.MAX_CONTEXT_BYTES, revision],
        ).fetchone()
        if row is None or row[2] is None or row[3] is None:
            raise Rejected("PARTITION_SILVER_SET_MISSING_OR_UNBOUNDED")
        # Include same-capture orphan rows or an illicit second revision, not only the good subset.
        totals = conn.execute(
            f"SELECT count(*),coalesce(sum(octet_length(record_bytes)),0) FROM {records} "
            "WHERE revision_id=? OR capture_id=?",
            [revision, row[1]],
        ).fetchone()
        if (
            totals is None
            or not 1 <= totals[0] <= codec.partitions.MAX_ROWS
            or totals[1] > codec.MAX_RECORD_TOTAL_BYTES
        ):
            raise Rejected("PARTITION_SILVER_COVERAGE_OR_BYTE_BOUND")
        stored = conn.execute(
            f"SELECT revision_id,ordinal,partition_index,partition_ordinal,"
            f"partition_payload_sha256,record_id,source_table,instrument_token,stored_ts,"
            f"volume,oi,CASE WHEN octet_length(record_bytes)<=? THEN record_bytes END,"
            f"source_observation_id,capture_id,recorded_at FROM {records} "
            "WHERE revision_id=? OR capture_id=? ORDER BY ordinal LIMIT ?",
            [codec.MAX_RECORD_BYTES, revision, row[1], codec.partitions.MAX_ROWS + 1],
        ).fetchall()
        links = conn.execute(
            f"SELECT * FROM {attempts} WHERE scope_id=? OR revision_id=? OR job_id=? "
            "ORDER BY job_id LIMIT 3",
            [row[0], revision, row[5]],
        ).fetchall()
        scoped = foundation._bounded_rows(
            conn,
            f"SELECT * FROM {jobs} WHERE scope_ref=? OR job_id=? ORDER BY job_id",
            ["sha256:" + row[0], row[5]],
            1,
        )
        history = foundation._bounded_rows(
            conn,
            f"SELECT * FROM {events} WHERE job_id=? ORDER BY event_index",
            [row[5]],
            3,
        )
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    try:
        pins = codec.PartitionBronzePins(**json.loads(bytes(row[2])))
    except (ValueError, TypeError, KeyError, RecursionError):
        raise Rejected("PARTITION_SILVER_SOURCE_PINS_MALFORMED") from None
    artifact = bytes(row[3])
    expected = codec.derive_partition_records(artifact, pins=pins)
    if (
        row[:2] != (pins.scope_id, pins.capture_id)
        or bytes(row[2]) != codec.canonical(asdict(pins))
        or _revision(pins, artifact, expected) != revision
        or row[4] != len(expected)
        or len(stored) != len(expected)
        or links != [(row[5], pins.scope_id, revision)]
    ):
        raise Rejected("PARTITION_SILVER_COMPLETE_COVERAGE_MISMATCH")
    for got, raw in zip(stored, expected, strict=True):
        if got != (revision, *codec.record_values(raw), row[6]):
            raise Rejected("PARTITION_SILVER_FULL_ROW_RECOMPUTATION_MISMATCH")
    if (
        len(scoped) != 1
        or scoped[0][0] != row[5]
        or scoped[0][1] is not None
        or scoped[0][2] != COMMAND
        or not scoped[0][3]
        or re.fullmatch(r"[a-f0-9]{40}", scoped[0][5]) is None
        or scoped[0][6] != _config(pins)
        or len(history) != 3
        or [(h[1], h[2], h[4]) for h in history]
        != [(1, "PLANNED", None), (2, "RUNNING", None), (3, "SUCCEEDED", None)]
    ):
        raise Rejected("PARTITION_SILVER_ORIGINAL_AUDIT_NOT_VERIFIED")
    codec.cells._clock(row[6])
    codec.cells._clock(scoped[0][7])
    for h in history:
        codec.cells._clock(h[3])
    metadata = [
        codec.VERSION,
        revision,
        row[:2],
        bytes(row[2]).hex(),
        codec.sha(artifact),
        row[4:],
        [[*r[:11], codec.sha(bytes(r[11])), *r[12:]] for r in stored],
        links,
        scoped,
        history,
    ]
    return codec.sha(foundation._json_bytes(metadata)), expected, pins, artifact


def read_partition_silver(
    silver: Any,
    *,
    revision_id: str,
    expected_recording_fingerprint: str,
) -> tuple[bytes, ...]:
    """Replay retained Silver evidence only; no current-Bronze or legacy-source assertion."""
    if not codec.pin(expected_recording_fingerprint):
        raise Rejected("EXACT_PARTITION_SILVER_RECORDING_PIN_REQUIRED")
    if silver.execute(
        "SELECT readonly FROM duckdb_databases() WHERE database_name=current_database()"
    ).fetchall() != [(True,)]:
        raise Rejected("READONLY_PARTITION_SILVER_REQUIRED")
    fingerprint, records, _pins, _artifact = _recording(silver, revision_id)
    if fingerprint != expected_recording_fingerprint:
        raise Rejected("PARTITION_SILVER_RECORDING_FINGERPRINT_CHANGED")
    return records


def revalidate_partition_silver(
    bronze: Any,
    silver: Any,
    *,
    revision_id: str,
    expected_recording_fingerprint: str,
) -> tuple[bytes, ...]:
    """Retained Silver plus actual current native Bronze; does not read current legacy SQL."""
    foundation._separate(bronze, silver)
    args = dict(
        revision_id=revision_id, expected_recording_fingerprint=expected_recording_fingerprint
    )
    first = read_partition_silver(silver, **args)
    pins = codec.PartitionBronzePins(**json.loads(first[0])["source_pins"])
    if codec.derive_partition_records(_observe(bronze, pins), pins=pins) != first:
        raise Rejected("PARTITION_BRONZE_CONTEXT_NO_LONGER_MATCHES")
    second = read_partition_silver(silver, **args)
    if first != second:
        raise Rejected("PARTITION_SILVER_CHANGED_DURING_REVALIDATION")
    return second


def revalidate_partition_silver_source(
    source: Any,
    bronze: Any,
    silver: Any,
    *,
    revision_id: str,
    expected_recording_fingerprint: str,
) -> tuple[bytes, ...]:
    """Separate opt-in current WHOLE legacy SQL revalidation, never pin refresh."""
    foundation._separate(source, silver)
    args = dict(
        revision_id=revision_id, expected_recording_fingerprint=expected_recording_fingerprint
    )
    first = revalidate_partition_silver(bronze, silver, **args)
    pins = codec.PartitionBronzePins(**json.loads(first[0])["source_pins"])
    bronze_source.revalidate_partitioned_legacy_recording(source, bronze, **pins.reader_arguments())
    second = revalidate_partition_silver(bronze, silver, **args)
    if first != second:
        raise Rejected("PARTITION_SILVER_CHANGED_DURING_SOURCE_REVALIDATION")
    return second
