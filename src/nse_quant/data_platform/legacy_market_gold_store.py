"""Audited native migrated-price Gold builds; persistence is not publication."""

from __future__ import annotations

import json
import platform
import re
from dataclasses import asdict
from datetime import UTC, datetime
from importlib.metadata import version
from typing import Any

from nse_quant.data_platform import legacy_market_gold as codec
from nse_quant.data_platform import legacy_market_partition_silver_store as source
from nse_quant.data_platform import legacy_market_silver_store as foundation
from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.contracts import DatasetContract, Layer, WritePolicy

COMMAND = "build.legacy_market_price_geometry@1"
CONTRACT = DatasetContract(
    "gold.legacy_price_features",
    "1",
    Layer.GOLD,
    WritePolicy.VERSIONED_BUILDS,
    ("build_id", "ordinal"),
    ("build_id", "ordinal", "event_ts", "published_at", "feature_version"),
    "native_migrated_legacy_price_geometry",
)
TABLES = {
    ("gold", n)
    for n in (
        "legacy_price_versions",
        "legacy_price_builds",
        "legacy_price_inputs",
        "legacy_price_features",
        "legacy_price_attempts",
    )
} | {("medallion_audit", n) for n in ("schema_versions", "dataset_contracts", "jobs", "job_events")}
name = foundation.name
Rejected = codec.GoldRejected


def _runtime() -> bytes:
    return codec.canonical(dict(python=platform.python_version(), duckdb=version("duckdb")))


def _definition() -> bytes:
    return codec.canonical([codec.DEFINITION, CONTRACT.canonical_json()])


def _owned(conn: Any, *, complete: bool) -> None:
    paths = conn.execute(
        "SELECT path FROM duckdb_databases() WHERE database_name=current_database()"
    ).fetchall()
    if len(paths) != 1 or not paths[0][0]:
        raise Rejected("FILE_BACKED_MIGRATED_GOLD_REQUIRED")
    rows = conn.execute(
        "SELECT table_schema,table_name,table_type FROM information_schema.tables "
        "WHERE table_catalog=current_database() ORDER BY table_schema,table_name LIMIT 10"
    ).fetchall()
    known = {(s, t) for s, t, _kind in rows}
    if known - TABLES or any(k != "BASE TABLE" for _, _, k in rows):
        raise Rejected("DEDICATED_MIGRATED_GOLD_REQUIRED")
    if complete and known != TABLES:
        raise Rejected("COMPLETE_MIGRATED_GOLD_SCHEMA_REQUIRED")


def initialize_legacy_price_gold(target: Any) -> None:
    """Explicit empty dedicated file only; interrupted initialization is not adopted."""
    _owned(target, complete=False)
    if target.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_catalog=current_database() LIMIT 1"
    ).fetchone():
        raise Rejected("EMPTY_MIGRATED_GOLD_INITIALIZATION_REQUIRED")
    AuditLedger(target).initialize()
    versions = name(target, "gold", "legacy_price_versions")
    builds = name(target, "gold", "legacy_price_builds")
    inputs = name(target, "gold", "legacy_price_inputs")
    features = name(target, "gold", "legacy_price_features")
    attempts = name(target, "gold", "legacy_price_attempts")
    target.execute("BEGIN TRANSACTION")
    try:
        target.execute(f"CREATE SCHEMA {versions.rsplit('.', 1)[0]}")
        target.execute(f"CREATE TABLE {versions} (version INTEGER PRIMARY KEY,definition BLOB)")
        target.execute(f"INSERT INTO {versions} VALUES (1,?)", [_definition()])
        target.execute(f"""CREATE TABLE {builds} (
            build_id VARCHAR PRIMARY KEY,scope_id VARCHAR UNIQUE NOT NULL,
            source_revision_id VARCHAR UNIQUE NOT NULL,source_pins BLOB NOT NULL,
            runtime_pins BLOB NOT NULL,input_count INTEGER NOT NULL,
            first_job_id VARCHAR NOT NULL,recorded_at TIMESTAMPTZ NOT NULL)""")
        target.execute(f"""CREATE TABLE {inputs} (
            build_id VARCHAR NOT NULL,source_revision_id VARCHAR NOT NULL,
            ordinal INTEGER NOT NULL,source_record_id VARCHAR NOT NULL,record_bytes BLOB NOT NULL,
            PRIMARY KEY(build_id,ordinal))""")
        target.execute(f"""CREATE TABLE {features} (
            build_id VARCHAR NOT NULL,source_revision_id VARCHAR NOT NULL,ordinal INTEGER NOT NULL,
            feature_id VARCHAR NOT NULL,source_record_id VARCHAR NOT NULL,
            source_table VARCHAR NOT NULL,
            instrument_token BIGINT NOT NULL,event_ts TIMESTAMPTZ NOT NULL,
            feature_version VARCHAR NOT NULL,published_at TIMESTAMPTZ,feature_bytes BLOB NOT NULL,
            recorded_at TIMESTAMPTZ NOT NULL,PRIMARY KEY(build_id,ordinal))""")
        target.execute(f"""CREATE TABLE {attempts} (
            job_id VARCHAR PRIMARY KEY,scope_id VARCHAR NOT NULL,build_id VARCHAR NOT NULL)""")
        target.execute("COMMIT")
    except BaseException:
        target.execute("ROLLBACK")
        raise
    AuditLedger(target).register_contract(CONTRACT)


def _schema(conn: Any) -> None:
    _owned(conn, complete=True)
    versions = name(conn, "gold", "legacy_price_versions")
    contracts = name(conn, "medallion_audit", "dataset_contracts")
    audit = name(conn, "medallion_audit", "schema_versions")
    if conn.execute(
        f"SELECT version,CASE WHEN octet_length(definition)<=32768 THEN definition END "
        f"FROM {versions} LIMIT 2"
    ).fetchall() != [(1, _definition())]:
        raise Rejected("MIGRATED_GOLD_DEFINITION_DRIFT")
    if conn.execute(
        f"SELECT fingerprint,CASE WHEN length(contract_json)<=32768 THEN contract_json END "
        f"FROM {contracts} WHERE dataset_name=? AND contract_version='1'",
        [CONTRACT.name],
    ).fetchall() != [(CONTRACT.fingerprint, CONTRACT.canonical_json())]:
        raise Rejected("MIGRATED_GOLD_CONTRACT_DRIFT")
    if conn.execute(f"SELECT version FROM {audit} LIMIT 2").fetchall() != [(1,)]:
        raise Rejected("MIGRATED_GOLD_AUDIT_SCHEMA_DRIFT")


def _observe(bronze: Any, silver: Any, pins: codec.GoldSourcePins) -> tuple[bytes, ...]:
    first = source.revalidate_partition_silver(bronze, silver, **pins.arguments())
    second = source.revalidate_partition_silver(bronze, silver, **pins.arguments())
    if first != second:
        raise Rejected("MIGRATED_GOLD_NATIVE_SOURCE_DRIFT")
    return first


def _config(pins: codec.GoldSourcePins, runtime: bytes) -> str:
    return codec.sha(codec.canonical([_definition().hex(), asdict(pins), runtime.hex()]))


def _build_id(
    pins: codec.GoldSourcePins,
    runtime: bytes,
    inputs: tuple[bytes, ...],
    rows: tuple[bytes, ...],
) -> str:
    return codec.sha(
        codec.canonical(
            [_config(pins, runtime), [codec.sha(r) for r in inputs], [codec.sha(r) for r in rows]]
        )
    )


def persist_legacy_price_gold(
    bronze: Any,
    silver: Any,
    gold: Any,
    *,
    pins: codec.GoldSourcePins,
    actor_id: str,
    code_revision: str,
) -> dict[str, Any]:
    """Actual revalidated native Silver -> recomputation -> complete audited domain build."""
    pins = codec.checked_pins(pins)
    if (
        type(actor_id) is not str
        or not 1 <= len(actor_id) <= 128
        or actor_id != actor_id.strip()
        or any(ord(c) < 32 for c in actor_id)
        or type(code_revision) is not str
        or re.fullmatch(r"[a-f0-9]{40}", code_revision) is None
    ):
        raise Rejected("EXPLICIT_MIGRATED_GOLD_EXECUTION_IDENTIFIERS_REQUIRED")
    foundation._separate(bronze, gold)
    foundation._separate(silver, gold)
    foundation._separate(bronze, silver)
    _schema(gold)
    builds = name(gold, "gold", "legacy_price_builds")
    inputs = name(gold, "gold", "legacy_price_inputs")
    features = name(gold, "gold", "legacy_price_features")
    attempts = name(gold, "gold", "legacy_price_attempts")
    jobs = name(gold, "medallion_audit", "jobs")
    if (
        gold.execute(
            f"SELECT 1 FROM {builds} WHERE scope_id=? OR source_revision_id=? LIMIT 1",
            [pins.scope_id, pins.revision_id],
        ).fetchone()
        or gold.execute(
            f"SELECT 1 FROM {attempts} WHERE scope_id=? LIMIT 1", [pins.scope_id]
        ).fetchone()
        or gold.execute(
            f"SELECT 1 FROM {jobs} WHERE scope_ref=? LIMIT 1", ["sha256:" + pins.scope_id]
        ).fetchone()
    ):
        raise Rejected("MIGRATED_GOLD_FIRST_WRITE_ORIGINAL_OBLIGATION")
    for table in (inputs, features):
        if gold.execute(
            f"SELECT 1 FROM {table} WHERE source_revision_id=? LIMIT 1", [pins.revision_id]
        ).fetchone():
            raise Rejected("MIGRATED_GOLD_ORPHAN_SOURCE_ROWS")
    runtime = _runtime()
    job = AuditLedger(gold).plan_job(
        command_name=COMMAND,
        actor_id=actor_id,
        code_revision=code_revision,
        scope_ref="sha256:" + pins.scope_id,
        config_hash=_config(pins, runtime),
    )
    with AuditLedger(gold).execution(job):
        source_rows = _observe(bronze, silver, pins)
        rows = codec.derive_gold_records(source_rows, pins=pins)
        if _observe(bronze, silver, pins) != source_rows:
            raise Rejected("MIGRATED_GOLD_NATIVE_SOURCE_DRIFT")
        build = _build_id(pins, runtime, source_rows, rows)
        at = datetime.now(UTC)
        gold.execute("BEGIN TRANSACTION")
        try:
            gold.execute(
                f"INSERT INTO {builds} VALUES (?,?,?,?,?,?,?,?)",
                [
                    build,
                    pins.scope_id,
                    pins.revision_id,
                    codec.canonical(asdict(pins)),
                    runtime,
                    len(rows),
                    job,
                    at,
                ],
            )
            for ordinal, (raw, feature) in enumerate(zip(source_rows, rows, strict=True)):
                gold.execute(
                    f"INSERT INTO {inputs} VALUES (?,?,?,?,?)",
                    [build, pins.revision_id, ordinal, codec.sha(raw), raw],
                )
                gold.execute(
                    f"INSERT INTO {features} VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    [build, pins.revision_id, *codec.feature_values(feature), at],
                )
            gold.execute(f"INSERT INTO {attempts} VALUES (?,?,?)", [job, pins.scope_id, build])
            gold.execute("COMMIT")
        except BaseException:
            gold.execute("ROLLBACK")
            raise
    fingerprint, _rows, _source, _pins = _recording(gold, build)
    return dict(
        build_id=build,
        recording_fingerprint=fingerprint,
        row_count=len(rows),
        feature_version=codec.FEATURE_VERSION,
        job_id=job,
        published=False,
        decision_eligibility_asserted=False,
    )


def _recording(
    conn: Any,
    build: str,
) -> tuple[str, tuple[bytes, ...], tuple[bytes, ...], codec.GoldSourcePins]:
    _schema(conn)
    if not codec.pin(build):
        raise Rejected("EXACT_MIGRATED_GOLD_BUILD_REQUIRED")
    builds = name(conn, "gold", "legacy_price_builds")
    inputs = name(conn, "gold", "legacy_price_inputs")
    features = name(conn, "gold", "legacy_price_features")
    attempts = name(conn, "gold", "legacy_price_attempts")
    jobs = name(conn, "medallion_audit", "jobs")
    events = name(conn, "medallion_audit", "job_events")
    conn.execute("BEGIN TRANSACTION")
    try:
        row = conn.execute(
            f"SELECT scope_id,source_revision_id,CASE WHEN octet_length(source_pins)<=512 "
            f"THEN source_pins END,CASE WHEN octet_length(runtime_pins)<=1024 "
            f"THEN runtime_pins END,"
            f"input_count,first_job_id,recorded_at FROM {builds} WHERE build_id=?",
            [build],
        ).fetchone()
        if row is None or row[2] is None or row[3] is None:
            raise Rejected("MIGRATED_GOLD_BUILD_MISSING_OR_UNBOUNDED")
        for table, column, bound in (
            (inputs, "record_bytes", codec.MAX_INPUT_TOTAL_BYTES),
            (features, "feature_bytes", codec.MAX_FEATURE_TOTAL_BYTES),
        ):
            totals = conn.execute(
                f"SELECT count(*),coalesce(sum(octet_length({column})),0) FROM {table} "
                "WHERE build_id=? OR source_revision_id=?",
                [build, row[1]],
            ).fetchone()
            if totals is None or not 1 <= totals[0] <= codec.MAX_ROWS or totals[1] > bound:
                raise Rejected("MIGRATED_GOLD_COVERAGE_OR_AGGREGATE_BYTE_BOUND")
        retained = conn.execute(
            f"SELECT build_id,source_revision_id,ordinal,source_record_id,"
            f"CASE WHEN octet_length(record_bytes)<=? THEN record_bytes END FROM {inputs} "
            "WHERE build_id=? OR source_revision_id=? ORDER BY ordinal LIMIT ?",
            [codec.MAX_INPUT_ROW_BYTES, build, row[1], codec.MAX_ROWS + 1],
        ).fetchall()
        stored = conn.execute(
            f"SELECT build_id,source_revision_id,ordinal,feature_id,source_record_id,source_table,"
            f"instrument_token,event_ts,feature_version,published_at,"
            f"CASE WHEN octet_length(feature_bytes)<=? THEN feature_bytes END,recorded_at "
            f"FROM {features} WHERE build_id=? OR source_revision_id=? ORDER BY ordinal LIMIT ?",
            [codec.MAX_FEATURE_ROW_BYTES, build, row[1], codec.MAX_ROWS + 1],
        ).fetchall()
        links = conn.execute(
            f"SELECT * FROM {attempts} WHERE scope_id=? OR build_id=? OR job_id=? "
            "ORDER BY job_id LIMIT 3",
            [row[0], build, row[5]],
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
        pins = codec.GoldSourcePins(**json.loads(bytes(row[2])))
    except (ValueError, TypeError, KeyError, RecursionError):
        raise Rejected("MIGRATED_GOLD_SOURCE_PINS_MALFORMED") from None
    if bytes(row[3]) != _runtime():
        raise Rejected("MIGRATED_GOLD_EXACT_REPLAY_RUNTIME_REQUIRED")
    if any(r[4] is None for r in retained):
        raise Rejected("MIGRATED_GOLD_SOURCE_ROW_BYTE_BOUND")
    source_rows = tuple(bytes(r[4]) for r in retained)
    expected = codec.derive_gold_records(source_rows, pins=pins)
    if (
        row[:2] != (pins.scope_id, pins.revision_id)
        or bytes(row[2]) != codec.canonical(asdict(pins))
        or _build_id(pins, bytes(row[3]), source_rows, expected) != build
        or row[4] != len(expected)
        or len(stored) != len(expected)
        or links != [(row[5], pins.scope_id, build)]
    ):
        raise Rejected("MIGRATED_GOLD_COMPLETE_COVERAGE_MISMATCH")
    for ordinal, (got_input, got, raw, feature) in enumerate(
        zip(retained, stored, source_rows, expected, strict=True)
    ):
        if got_input != (build, pins.revision_id, ordinal, codec.sha(raw), raw) or got != (
            build,
            pins.revision_id,
            *codec.feature_values(feature),
            row[6],
        ):
            raise Rejected("MIGRATED_GOLD_FULL_ROW_RECOMPUTATION_MISMATCH")
    if (
        len(scoped) != 1
        or scoped[0][0] != row[5]
        or scoped[0][1] is not None
        or scoped[0][2] != COMMAND
        or not scoped[0][3]
        or re.fullmatch(r"[a-f0-9]{40}", scoped[0][5]) is None
        or scoped[0][6] != _config(pins, bytes(row[3]))
        or len(history) != 3
        or [(h[1], h[2], h[4]) for h in history]
        != [(1, "PLANNED", None), (2, "RUNNING", None), (3, "SUCCEEDED", None)]
    ):
        raise Rejected("MIGRATED_GOLD_ORIGINAL_AUDIT_NOT_VERIFIED")
    codec.silver.cells._clock(row[6])
    codec.silver.cells._clock(scoped[0][7])
    for h in history:
        codec.silver.cells._clock(h[3])
    metadata = [
        codec.VERSION,
        build,
        row[:2],
        bytes(row[2]).hex(),
        bytes(row[3]).hex(),
        row[4:],
        [[*r[:4], codec.sha(bytes(r[4]))] for r in retained],
        [[*r[:10], codec.sha(bytes(r[10])), r[11]] for r in stored],
        links,
        scoped,
        history,
    ]
    return codec.sha(foundation._json_bytes(metadata)), expected, source_rows, pins


def read_legacy_price_gold(
    gold: Any,
    *,
    build_id: str,
    expected_recording_fingerprint: str,
) -> tuple[bytes, ...]:
    """Full retained Gold replay; NOT a current upstream or publication assertion."""
    if not codec.pin(expected_recording_fingerprint):
        raise Rejected("EXACT_MIGRATED_GOLD_RECORDING_PIN_REQUIRED")
    if gold.execute(
        "SELECT readonly FROM duckdb_databases() WHERE database_name=current_database()"
    ).fetchall() != [(True,)]:
        raise Rejected("READONLY_MIGRATED_GOLD_REQUIRED")
    fingerprint, rows, _source, _pins = _recording(gold, build_id)
    if fingerprint != expected_recording_fingerprint:
        raise Rejected("MIGRATED_GOLD_RECORDING_FINGERPRINT_CHANGED")
    return rows


def revalidate_legacy_price_gold(
    bronze: Any,
    silver: Any,
    gold: Any,
    *,
    build_id: str,
    expected_recording_fingerprint: str,
) -> tuple[bytes, ...]:
    """Retained Gold plus actual current native Bronze/Silver, never a legacy SQL claim."""
    foundation._separate(bronze, gold)
    foundation._separate(silver, gold)
    args = dict(build_id=build_id, expected_recording_fingerprint=expected_recording_fingerprint)
    first = read_legacy_price_gold(gold, **args)
    pins = codec.GoldSourcePins(**json.loads(first[0])["source_pins"])
    observed = codec.derive_gold_records(_observe(bronze, silver, pins), pins=pins)
    if observed != first:
        raise Rejected("MIGRATED_GOLD_CURRENT_SOURCE_CHANGED")
    second = read_legacy_price_gold(gold, **args)
    if first != second:
        raise Rejected("MIGRATED_GOLD_CHANGED_DURING_REVALIDATION")
    return second
