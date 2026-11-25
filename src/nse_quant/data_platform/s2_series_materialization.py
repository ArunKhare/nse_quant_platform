"""Audited offline S2 series retention, not Gold publication or eligibility.

Caller owns a dedicated file-backed writer. No ambient transaction, adoption,
repair, latest-pointer selection or external side effects are implicit.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.contracts import DatasetContract, Layer, WritePolicy

VERSION = "s2-series-materialization@1"
COMMAND = "persist.s2_series_materialization@1"
EOD = "india_vix_eod_history"
MINUTE = "india_vix_minute_bars"
MAX_BYTES = 6 * 1024 * 1024
MAX_VARIANTS = 64
TABLE = "s2_series_materializations"
DEFINITION_TABLE = "s2_series_materialization_definition"
CONTRACT = DatasetContract(
    "silver.s2_series_materializations",
    "1",
    Layer.SILVER,
    WritePolicy.APPEND_REVISIONS,
    ("revision_id",),
    ("revision_id", "source_observation_id", "recorded_at"),
    "s2_series_materialization",
)
DEFINITION = [
    VERSION,
    COMMAND,
    CONTRACT.canonical_json(),
    "retained-research-only;no-healing;scope-conflicts-block-replay@1",
]


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _pin(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _actor(actor: str, revision: str) -> None:
    if (
        type(actor) is not str
        or not 0 < len(actor.encode()) <= 128
        or type(revision) is not str
        or re.fullmatch(r"[a-f0-9]{40}", revision) is None
    ):
        raise ValueError("S2_EXPLICIT_ACTOR_AND_CODE_REVISION_REQUIRED")


def _file(conn: Any, *, readonly: bool | None = None) -> Path:
    rows = conn.execute(
        "SELECT path,readonly FROM duckdb_databases() WHERE database_name=current_database()"
    ).fetchall()
    if len(rows) != 1 or not rows[0][0]:
        raise ValueError("S2_FILE_BACKED_STORE_REQUIRED")
    if readonly is not None and rows[0][1] is not readonly:
        raise ValueError("S2_READONLY_REQUIRED" if readonly else "S2_EXCLUSIVE_WRITER_REQUIRED")
    return Path(rows[0][0]).resolve()


def _separate(*connections: Any) -> None:
    paths = [_file(conn) for conn in connections if conn is not None]
    for index, path in enumerate(paths):
        for other in paths[index + 1 :]:
            if path == other or path.samefile(other):
                raise ValueError("S2_SEPARATE_STORES_REQUIRED")


def _name(conn: Any, table: str, schema: str = "silver") -> str:
    catalog = conn.execute("SELECT current_database()").fetchone()[0]
    return ".".join('"' + value.replace('"', '""') + '"' for value in (catalog, schema, table))


def _inventory(conn: Any) -> set[tuple[str, str, str]]:
    rows = conn.execute(
        "SELECT table_schema,table_name,table_type FROM information_schema.tables "
        "WHERE table_catalog=current_database() LIMIT 8"
    ).fetchall()
    return set(rows)


def initialize(target: Any, *, actor_id: str, code_revision: str) -> None:
    """Explicit new empty store only. Never adopt or silently migrate an existing one."""
    _actor(actor_id, code_revision)
    _file(target, readonly=False)
    if _inventory(target):
        raise ValueError("S2_EMPTY_DEDICATED_STORE_REQUIRED")
    # The shared audit initializer uses unqualified schema references.
    catalog = target.execute("SELECT current_database()").fetchone()[0]
    if catalog in {"silver", "medallion_audit"}:
        raise ValueError("S2_RESERVED_CATALOG_NAME")
    ledger = AuditLedger(target)
    ledger.initialize()
    target.execute("BEGIN TRANSACTION")
    try:
        schema = _name(target, TABLE).rsplit(".", 1)[0]
        target.execute(f"CREATE SCHEMA {schema}")
        target.execute(
            f"CREATE TABLE {_name(target, DEFINITION_TABLE)} (version INTEGER PRIMARY KEY, definition BLOB NOT NULL)"
        )
        target.execute(f"INSERT INTO {_name(target, DEFINITION_TABLE)} VALUES (1,?)", [canonical(DEFINITION)])
        target.execute(
            f"CREATE TABLE {_name(target, TABLE)} ("
            "revision_id VARCHAR PRIMARY KEY,scope VARCHAR NOT NULL,digest VARCHAR NOT NULL,"
            "source_observation_id VARCHAR NOT NULL,kind VARCHAR NOT NULL,body BLOB NOT NULL,"
            "job_id VARCHAR NOT NULL UNIQUE,recorded_at TIMESTAMPTZ NOT NULL,UNIQUE(scope,digest))"
        )
        target.execute("COMMIT")
    except BaseException:
        target.execute("ROLLBACK")
        raise
    ledger.register_contract(CONTRACT)
    _store(target)


def _store(conn: Any) -> None:
    _file(conn)
    expected = {("silver", name, "BASE TABLE") for name in (TABLE, DEFINITION_TABLE)} | {
        ("medallion_audit", name, "BASE TABLE")
        for name in ("schema_versions", "dataset_contracts", "jobs", "job_events")
    }
    if _inventory(conn) != expected:
        raise ValueError("S2_DEDICATED_STORE_INVENTORY_MISMATCH")
    shapes = {
        TABLE: ("revision_id", "scope", "digest", "source_observation_id", "kind", "body", "job_id", "recorded_at"),
        DEFINITION_TABLE: ("version", "definition"),
    }
    for table, expected_columns in shapes.items():
        columns = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_catalog=current_database() AND table_schema='silver' "
            "AND table_name=? ORDER BY ordinal_position LIMIT 10",
            [table],
        ).fetchall()
        if tuple(row[0] for row in columns) != expected_columns:
            raise ValueError("S2_MATERIALIZATION_COLUMN_DRIFT")
    definition = conn.execute(
        f"SELECT version,CASE WHEN octet_length(definition)<=32768 "
        f"THEN definition END FROM {_name(conn, DEFINITION_TABLE)} LIMIT 2"
    ).fetchall()
    if definition != [(1, canonical(DEFINITION))]:
        raise ValueError("S2_DEFINITION_DRIFT")
    contracts = conn.execute(
        f"SELECT dataset_name,contract_version,fingerprint,contract_json "
        f"FROM {_name(conn, 'dataset_contracts', 'medallion_audit')} LIMIT 2"
    ).fetchall()
    if contracts != [(CONTRACT.name, CONTRACT.version, CONTRACT.fingerprint, CONTRACT.canonical_json())]:
        raise ValueError("S2_DATASET_CONTRACT_DRIFT")
    if conn.execute(f"SELECT version FROM {_name(conn, 'schema_versions', 'medallion_audit')} LIMIT 2").fetchall() != [
        (1,)
    ]:
        raise ValueError("S2_AUDIT_VERSION_DRIFT")
    events, jobs = (_name(conn, name, "medallion_audit") for name in ("job_events", "jobs"))
    if conn.execute(
        f"SELECT 1 FROM {events} e LEFT JOIN {jobs} j USING(job_id) WHERE j.job_id IS NULL LIMIT 1"
    ).fetchone():
        raise ValueError("S2_ORPHAN_AUDIT_EVENT")


def _wrap(kind: str, content: dict[str, Any]) -> bytes:
    raw = canonical(
        dict(
            version=VERSION,
            kind=kind,
            content=content,
            iv30_source="india_vix",
            publication_asserted=False,
            decision_eligibility_asserted=False,
            atomic_cross_database_snapshot_asserted=False,
        )
    )
    if not 0 < len(raw) <= MAX_BYTES:
        raise ValueError("S2_MATERIALIZATION_BYTE_BOUND")
    return raw


def prepare_eod(history: bytes) -> bytes:
    from nse_quant.analytics import s2_iv30_history as eod

    return _wrap(EOD, eod.replay_history(history, expected_sha256=sha(history)))


def prepare_minutes(bronze: Any, vix_silver: Any, *, revision_ids: list[str]) -> bytes:
    from nse_quant.data_platform import s2_vix_minute_bars as minute

    _file(bronze, readonly=True)
    _file(vix_silver, readonly=True)
    _separate(bronze, vix_silver)
    raw = minute.build_minute_bars(bronze, vix_silver, revision_ids=revision_ids)
    if not 0 < len(raw) <= 2 * 1024 * 1024:
        raise ValueError("S2_MINUTE_ARTIFACT_BYTE_BOUND")
    return _wrap(MINUTE, json.loads(raw))


def _reproduce(raw: bytes, *, bronze: Any = None, vix_silver: Any = None) -> dict[str, Any]:
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_BYTES:
        raise ValueError("S2_MATERIALIZATION_BYTE_BOUND")
    doc = json.loads(raw)
    if (
        type(doc) is not dict
        or canonical(doc) != raw
        or set(doc)
        != {
            "version",
            "kind",
            "content",
            "iv30_source",
            "publication_asserted",
            "decision_eligibility_asserted",
            "atomic_cross_database_snapshot_asserted",
        }
    ):
        raise ValueError("S2_EXACT_CANONICAL_MATERIALIZATION_REQUIRED")
    if doc["kind"] == EOD:
        expected = prepare_eod(canonical(doc["content"]))
    elif doc["kind"] == MINUTE:
        if bronze is None or vix_silver is None:
            raise ValueError("S2_NATIVE_MINUTE_REPLAY_SOURCES_REQUIRED")
        expected = prepare_minutes(bronze, vix_silver, revision_ids=doc["content"]["revisions"])
    else:
        raise ValueError("S2_UNSUPPORTED_SERIES_KIND")
    if raw != expected:
        raise ValueError("S2_MATERIALIZATION_RECOMPUTE_MISMATCH")
    return doc


def _scope(kind: str, observation_id: str) -> str:
    if not _pin(observation_id):
        raise ValueError("S2_EXACT_OBSERVATION_ID_REQUIRED")
    return sha(canonical([VERSION, kind, observation_id]))


def _source(doc: dict[str, Any]) -> str:
    content = doc["content"]
    return sha(canonical(content["request"] if doc["kind"] == EOD else content["revisions"]))


def _audit(conn: Any, job: str, scope: str, digest: str, recorded_at: datetime) -> None:
    jobs, events = (_name(conn, name, "medallion_audit") for name in ("jobs", "job_events"))
    rows = conn.execute(
        f"SELECT command_name,scope_ref,config_hash,actor_id,code_revision,"
        f"parent_job_id,created_at FROM {jobs} WHERE job_id=? LIMIT 2",
        [job],
    ).fetchall()
    if len(rows) != 1:
        raise ValueError("S2_EXACT_ORIGINAL_AUDIT_REQUIRED")
    row = rows[0]
    _actor(row[3], row[4])
    if row[:3] != (COMMAND, scope, digest) or row[5] is not None:
        raise ValueError("S2_AUDIT_IDENTITY_MISMATCH")
    history = conn.execute(
        f"SELECT event_index,state,recorded_at,reason_code FROM {events} WHERE job_id=? ORDER BY event_index LIMIT 4",
        [job],
    ).fetchall()
    if [(r[0], r[1], r[3]) for r in history] != [(1, "PLANNED", None), (2, "RUNNING", None), (3, "SUCCEEDED", None)]:
        raise ValueError("S2_SUCCESSFUL_ORIGINAL_AUDIT_REQUIRED")
    clocks = [row[6], *(r[2] for r in history)]
    if any(not isinstance(at, datetime) or at.utcoffset() is None for at in [*clocks, recorded_at]):
        raise ValueError("S2_AWARE_AUDIT_CLOCK_REQUIRED")
    if clocks != sorted(clocks) or not history[1][2] <= recorded_at <= history[2][2]:
        raise ValueError("S2_AUDIT_TIME_ORDER")


def _rows(conn: Any, scope: str):
    _store(conn)
    table = _name(conn, TABLE)
    rows = conn.execute(
        f"SELECT revision_id,digest,source_observation_id,kind,"
        "CASE WHEN octet_length(body)<=? THEN body END,job_id,recorded_at "
        f"FROM {table} WHERE scope=? ORDER BY digest LIMIT ?",
        [MAX_BYTES, scope, MAX_VARIANTS + 1],
    ).fetchall()
    jobs = conn.execute(
        f"SELECT job_id,config_hash FROM {_name(conn, 'jobs', 'medallion_audit')} "
        "WHERE command_name=? AND scope_ref=? LIMIT ?",
        [COMMAND, scope, MAX_VARIANTS + 1],
    ).fetchall()
    if len(rows) > MAX_VARIANTS or len(rows) != len(jobs) or {(r[5], r[1]) for r in rows} != set(jobs):
        raise ValueError("S2_ORPHAN_OR_INTERRUPTED_MATERIALIZATION")
    for revision, digest, source, kind, body, job, at in rows:
        if body is None or not _pin(digest) or sha(bytes(body)) != digest:
            raise ValueError("S2_MATERIALIZATION_INTEGRITY_MISMATCH")
        doc = json.loads(bytes(body))
        if (
            canonical(doc) != bytes(body)
            or doc.get("version") != VERSION
            or doc.get("kind") != kind
            or revision != sha(canonical([VERSION, scope, digest]))
            or source != _source(doc)
        ):
            raise ValueError("S2_MATERIALIZATION_METADATA_MISMATCH")
        _audit(conn, job, scope, digest, at)
    return rows


def _insert(target: Any, values: list[Any]) -> None:
    target.execute(f"INSERT INTO {_name(target, TABLE)} VALUES (?,?,?,?,?,?,?,?)", values)


def persist(
    target: Any,
    *,
    raw: bytes,
    observation_id: str,
    expected_sha256: str,
    actor_id: str,
    code_revision: str,
    bronze: Any = None,
    vix_silver: Any = None,
) -> dict[str, Any]:
    _actor(actor_id, code_revision)
    _file(target, readonly=False)
    _separate(target, bronze, vix_silver)
    if (
        not _pin(expected_sha256)
        or type(raw) is not bytes
        or not 0 < len(raw) <= MAX_BYTES
        or sha(raw) != expected_sha256
    ):
        raise ValueError("S2_REVIEWED_MATERIALIZATION_CHANGED")
    doc = _reproduce(raw, bronze=bronze, vix_silver=vix_silver)
    scope = _scope(doc["kind"], observation_id)
    rows = _rows(target, scope)
    existing = next((row for row in rows if row[1] == expected_sha256), None)
    revision = sha(canonical([VERSION, scope, expected_sha256]))
    if existing is not None:
        if bytes(existing[4]) != raw:
            raise ValueError("S2_EXACT_RETRY_MISMATCH")
    else:
        if len(rows) >= MAX_VARIANTS:
            raise ValueError("S2_MATERIALIZATION_VARIANT_BOUND")
        ledger = AuditLedger(target)
        job = ledger.plan_job(
            command_name=COMMAND,
            actor_id=actor_id,
            code_revision=code_revision,
            scope_ref=scope,
            config_hash=expected_sha256,
        )
        with ledger.execution(job):
            _reproduce(raw, bronze=bronze, vix_silver=vix_silver)
            target.execute("BEGIN TRANSACTION")
            try:
                _insert(
                    target, [revision, scope, expected_sha256, _source(doc), doc["kind"], raw, job, datetime.now(UTC)]
                )
                target.execute("COMMIT")
            except BaseException:
                target.execute("ROLLBACK")
                raise
    final = _rows(target, scope)
    if {row[1] for row in final} != {row[1] for row in rows} | {expected_sha256}:
        raise ValueError("S2_MATERIALIZATION_FINAL_AUDIT_MISMATCH")
    return dict(
        revision_id=revision,
        digest=expected_sha256,
        kind=doc["kind"],
        exact_retry=existing is not None,
        conflicted=len(final) > 1,
        publication_asserted=False,
        decision_eligibility_asserted=False,
    )


def replay(
    reader: Any, *, kind: str, observation_id: str, expected_sha256: str, bronze: Any = None, vix_silver: Any = None
) -> bytes:
    _file(reader, readonly=True)
    _separate(reader, bronze, vix_silver)
    if kind not in {EOD, MINUTE} or not _pin(expected_sha256):
        raise ValueError("S2_EXACT_KIND_AND_DIGEST_REQUIRED")
    scope = _scope(kind, observation_id)
    rows = _rows(reader, scope)
    if len(rows) != 1 or rows[0][1] != expected_sha256:
        raise ValueError("S2_MISSING_CONFLICTED_OR_WRONG_MATERIALIZATION_PIN")
    raw = bytes(rows[0][4])
    _reproduce(raw, bronze=bronze, vix_silver=vix_silver)
    if _rows(reader, scope) != rows:
        raise ValueError("S2_MATERIALIZATION_FINAL_AUDIT_MISMATCH")
    return raw
