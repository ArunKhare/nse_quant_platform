"""Persisted audited decision-run coverage reconciliation Silver.

Records an immutable reconciliation between an audited native decision run and
the current Silver-backed coverage report. Replays the exact reconciliation.
No eligibility, live trading, healing, backfill, adoption, or execution
authority. POINT_IN_TIME_DECISION remains rejected.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.contracts import DatasetContract, Layer, WritePolicy
from nse_quant.data_platform.native_strategy_input_coverage import Rejected
from nse_quant.data_platform.native_strategy_requirements import (
    STRATEGY,
)

VERSION = "native-audited-decision-reconciliation-silver-recording@1"
COMMAND = "record.native_audited_decision_reconciliation@1"
MAX_CONTEXT_BYTES = 1_048_576
MAX_RECORD_BYTES = 262_144
DOMAIN = (
    "audited_decision_reconciliation_versions",
    "audited_decision_reconciliation_sets",
    "audited_decision_reconciliation_observations",
    "audited_decision_reconciliation_attempts",
)
TABLES = {("silver", name) for name in DOMAIN} | {
    ("medallion_audit", name) for name in ("schema_versions", "dataset_contracts", "jobs", "job_events")
}
CONTRACT = DatasetContract(
    "silver.native_audited_decision_reconciliation_observations",
    "1",
    Layer.SILVER,
    WritePolicy.APPEND_REVISIONS,
    ("revision_id", "ordinal"),
    (
        "revision_id",
        "ordinal",
        "run_id",
        "source_observation_id",
        "recorded_at",
        "record_bytes",
    ),
    "native_audited_decision_reconciliation",
)
DEFINITION = (
    VERSION,
    COMMAND,
    CONTRACT.canonical_json(),
    MAX_CONTEXT_BYTES,
    MAX_RECORD_BYTES,
    "immutable reconciliation of an audited decision run and coverage report",
    "POINT_IN_TIME_DECISION remains rejected",
    "no eligibility, execution authority, healing, backfill, or adoption",
)


def _pin(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        ensure_ascii=False,
    ).encode("utf-8")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _table(target: Any, name: str) -> str:
    return f"silver.{name}"


def _owned(target: Any, *, complete: bool) -> None:
    paths = target.execute("SELECT path FROM duckdb_databases() WHERE database_name=current_database()").fetchall()
    if len(paths) != 1 or not paths[0][0]:
        raise Rejected("FILE_BACKED_RECONCILIATION_SILVER_REQUIRED")
    rows = target.execute(
        "SELECT table_schema,table_name,table_type FROM information_schema.tables "
        "WHERE table_catalog=current_database() LIMIT 9"
    ).fetchall()
    known = {(schema, table) for schema, table, _kind in rows}
    if known - TABLES or any(kind != "BASE TABLE" for _schema, _table, kind in rows) or (complete and known != TABLES):
        raise Rejected("DEDICATED_RECONCILIATION_SILVER_REQUIRED")


def initialize_audited_decision_reconciliation_silver(target: Any) -> None:
    """Initialize an explicitly empty dedicated reconciliation Silver target."""
    _owned(target, complete=False)
    if target.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_catalog=current_database() LIMIT 1"
    ).fetchone():
        raise Rejected("EMPTY_RECONCILIATION_SILVER_INITIALIZATION_REQUIRED")

    AuditLedger(target).initialize()
    versions, sets, observations, attempts = (_table(target, n) for n in DOMAIN)
    target.execute("BEGIN TRANSACTION")
    try:
        target.execute("CREATE SCHEMA silver")
        target.execute(f"CREATE TABLE {versions} (version INTEGER PRIMARY KEY,definition BLOB NOT NULL)")
        target.execute(f"INSERT INTO {versions} VALUES (1,?)", [_canonical(DEFINITION)])
        target.execute(
            f"CREATE TABLE {sets} ("
            "revision_id VARCHAR PRIMARY KEY,"
            "run_id VARCHAR NOT NULL,"
            "coverage_revision_id VARCHAR NOT NULL,"
            "coverage_recording_fingerprint VARCHAR NOT NULL,"
            "context BLOB NOT NULL,"
            "first_job_id VARCHAR NOT NULL,"
            "recorded_at TIMESTAMPTZ NOT NULL)"
        )
        target.execute(
            f"CREATE TABLE {observations} ("
            "revision_id VARCHAR NOT NULL,"
            "ordinal INTEGER NOT NULL,"
            "run_id VARCHAR NOT NULL,"
            "source_observation_id VARCHAR NOT NULL,"
            "record_bytes BLOB NOT NULL,"
            "recorded_at TIMESTAMPTZ NOT NULL,"
            "PRIMARY KEY(revision_id,ordinal),"
            "UNIQUE(revision_id,run_id))"
        )
        target.execute(
            f"CREATE TABLE {attempts} (job_id VARCHAR PRIMARY KEY,run_id VARCHAR NOT NULL,revision_id VARCHAR NOT NULL)"
        )
        target.execute("COMMIT")
    except BaseException:
        target.execute("ROLLBACK")
        raise
    AuditLedger(target).register_contract(CONTRACT)


def _schema(target: Any) -> None:
    _owned(target, complete=True)
    versions = _table(target, DOMAIN[0])
    contracts = "medallion_audit.dataset_contracts"
    audit = "medallion_audit.schema_versions"
    if target.execute(
        f"SELECT version,CASE WHEN octet_length(definition)<=32768 THEN definition END FROM {versions} LIMIT 2"
    ).fetchall() != [(1, _canonical(DEFINITION))]:
        raise Rejected("RECONCILIATION_SILVER_DEFINITION_DRIFT")
    if target.execute(
        "SELECT CASE WHEN length(fingerprint)<=64 THEN fingerprint END,"
        "CASE WHEN octet_length(encode(contract_json))<=32768 "
        f"THEN contract_json END FROM {contracts} "
        "WHERE dataset_name=? AND contract_version='1'",
        [CONTRACT.name],
    ).fetchall() != [(CONTRACT.fingerprint, CONTRACT.canonical_json())]:
        raise Rejected("RECONCILIATION_SILVER_CONTRACT_DRIFT")
    if target.execute(f"SELECT version FROM {audit} LIMIT 2").fetchall() != [(1,)]:
        raise Rejected("RECONCILIATION_SILVER_AUDIT_SCHEMA_DRIFT")


def _validate_reconciliation(reconciliation: dict[str, Any]) -> None:
    if type(reconciliation) is not dict:
        raise Rejected("RECONCILIATION_DOCUMENT_REQUIRED")
    if reconciliation.get("version") != VERSION:
        raise Rejected("RECONCILIATION_VERSION_MISMATCH")
    if reconciliation.get("strategy") != STRATEGY:
        raise Rejected("RECONCILIATION_STRATEGY_MISMATCH")
    coverage = reconciliation.get("coverage")
    if type(coverage) is not dict:
        raise Rejected("RECONCILIATION_COVERAGE_REQUIRED")
    if coverage.get("revision_id") != reconciliation.get("coverage_revision_id"):
        raise Rejected("RECONCILIATION_COVERAGE_REVISION_MISMATCH")
    if coverage.get("recording_fingerprint") != reconciliation.get("coverage_recording_fingerprint"):
        raise Rejected("RECONCILIATION_COVERAGE_FINGERPRINT_MISMATCH")
    if reconciliation.get("complete") is True:
        raise Rejected("RECONCILIATION_COMPLETION_NOT_ASSERTABLE")
    if reconciliation.get("decision_eligibility_asserted") is not False:
        raise Rejected("RECONCILIATION_ELIGIBILITY_FORBIDDEN")
    stages = reconciliation.get("stages")
    if type(stages) is not list or not stages:
        raise Rejected("RECONCILIATION_STAGES_REQUIRED")
    for stage in stages:
        if type(stage) is not dict:
            raise Rejected("RECONCILIATION_STAGE_DOCUMENT_REQUIRED")
        if stage.get("decision_eligibility_asserted") is not False:
            raise Rejected("RECONCILIATION_STAGE_ELIGIBILITY_FORBIDDEN")


def reconciliation_context(reconciliation: dict[str, Any]) -> str:
    """Return the exact context hash for a reconciliation document."""
    _validate_reconciliation(reconciliation)
    return _sha(_canonical(reconciliation))


def _revision(context: bytes, record: bytes) -> str:
    return _sha(
        _canonical(
            [
                _sha(_canonical(DEFINITION)),
                _sha(context),
                _sha(record),
            ]
        )
    )


def record_audited_decision_reconciliation(
    target: Any,
    *,
    reconciliation: dict[str, Any],
    expected_context_sha256: str,
    actor_id: str,
    code_revision: str,
) -> dict[str, Any]:
    """Record one immutable decision-run coverage reconciliation."""
    _validate_reconciliation(reconciliation)
    if not _pin(expected_context_sha256):
        raise Rejected("EXACT_EXPECTED_CONTEXT_PIN_REQUIRED")
    if type(actor_id) is not str or not actor_id:
        raise Rejected("EXACT_ACTOR_REQUIRED")
    if type(code_revision) is not str or not code_revision:
        raise Rejected("EXACT_CODE_REVISION_REQUIRED")

    context = _canonical(reconciliation)
    if _sha(context) != expected_context_sha256:
        raise Rejected("REVIEWED_RECONCILIATION_CONTEXT_CHANGED")
    if len(context) > MAX_CONTEXT_BYTES:
        raise Rejected("RECONCILIATION_CONTEXT_BYTE_BOUND")

    run_id = reconciliation["run_id"]
    _schema(target)
    sets = _table(target, DOMAIN[1])
    observations = _table(target, DOMAIN[2])
    attempts = _table(target, DOMAIN[3])
    jobs = "medallion_audit.jobs"

    for table, field, value in (
        (sets, "run_id", run_id),
        (attempts, "run_id", run_id),
        (jobs, "scope_ref", "sha256:" + run_id),
        (observations, "run_id", run_id),
    ):
        if target.execute(f'SELECT 1 FROM {table} WHERE "{field}"=? LIMIT 1', [value]).fetchone():
            raise Rejected("RECONCILIATION_FIRST_WRITE_OR_ORPHAN_OBLIGATION")

    record = _canonical(reconciliation)
    if not 0 < len(record) <= MAX_RECORD_BYTES:
        raise Rejected("RECONCILIATION_RECORD_BYTE_BOUND")
    revision = _revision(context, record)
    ledger = AuditLedger(target)
    config = _sha(_canonical([DEFINITION, expected_context_sha256]))
    job = ledger.plan_job(
        command_name=COMMAND,
        actor_id=actor_id,
        code_revision=code_revision,
        scope_ref="sha256:" + run_id,
        config_hash=config,
    )
    with ledger.execution(job):
        target.execute("BEGIN TRANSACTION")
        try:
            target.execute(
                f"INSERT INTO {sets} VALUES (?,?,?,?,?,?,?)",
                [
                    revision,
                    run_id,
                    reconciliation["coverage_revision_id"],
                    reconciliation["coverage_recording_fingerprint"],
                    context,
                    job,
                    datetime.now(UTC),
                ],
            )
            target.execute(
                f"INSERT INTO {observations} VALUES (?,?,?,?,?,?)",
                [
                    revision,
                    0,
                    run_id,
                    run_id + ":reconciliation",
                    record,
                    datetime.now(UTC),
                ],
            )
            target.execute(
                f"INSERT INTO {attempts} VALUES (?,?,?)",
                [job, run_id, revision],
            )
            target.execute("COMMIT")
        except BaseException:
            target.execute("ROLLBACK")
            raise

    return {
        "revision_id": revision,
        "recording_fingerprint": _recording_fingerprint(target, revision),
        "job_id": job,
        "decision_eligibility_asserted": False,
    }


def _recording_fingerprint(target: Any, revision_id: str) -> str:
    if not _pin(revision_id):
        raise Rejected("EXACT_RECONCILIATION_REVISION_REQUIRED")
    _schema(target)
    sets = _table(target, DOMAIN[1])
    observations = _table(target, DOMAIN[2])
    row = target.execute(
        f"SELECT context FROM {sets} WHERE revision_id=? LIMIT 2",
        [revision_id],
    ).fetchall()
    if len(row) != 1:
        raise Rejected("RECONCILIATION_EXACT_SET_REQUIRED")
    context = bytes(row[0][0])
    records = target.execute(
        f"SELECT record_bytes FROM {observations} WHERE revision_id=? ORDER BY ordinal LIMIT 2",
        [revision_id],
    ).fetchall()
    if len(records) != 1:
        raise Rejected("RECONCILIATION_RECORD_COVERAGE_MISMATCH")
    return _sha(
        _canonical(
            [
                _sha(_canonical(DEFINITION)),
                _sha(context),
                _sha(bytes(records[0][0])),
            ]
        )
    )


def replay_audited_decision_reconciliation(
    target: Any,
    *,
    run_id: str,
    expected_revision_id: str,
    expected_recording_fingerprint: str,
) -> dict[str, Any]:
    """Exactly replay a persisted decision-run coverage reconciliation."""
    if type(run_id) is not str or not run_id:
        raise Rejected("EXACT_RUN_ID_REQUIRED")
    if not _pin(expected_revision_id):
        raise Rejected("EXACT_REVISION_PIN_REQUIRED")
    if not _pin(expected_recording_fingerprint):
        raise Rejected("EXACT_RECORDING_FINGERPRINT_REQUIRED")

    _schema(target)
    sets = _table(target, DOMAIN[1])
    observations = _table(target, DOMAIN[2])
    row = target.execute(
        f"SELECT revision_id,context FROM {sets} WHERE run_id=? LIMIT 2",
        [run_id],
    ).fetchall()
    if len(row) != 1:
        raise Rejected("RECONCILIATION_EXACT_SET_REQUIRED")
    revision_id, context_bytes = row[0]
    if revision_id != expected_revision_id:
        raise Rejected("RECONCILIATION_REVISION_MISMATCH")
    actual = _recording_fingerprint(target, revision_id)
    if actual != expected_recording_fingerprint:
        raise Rejected("RECONCILIATION_RECORDING_FINGERPRINT_CHANGED")

    records = target.execute(
        f"SELECT record_bytes FROM {observations} WHERE revision_id=? AND run_id=? LIMIT 2",
        [revision_id, run_id],
    ).fetchall()
    if len(records) != 1:
        raise Rejected("RECONCILIATION_RECORD_COVERAGE_MISMATCH")
    record = bytes(records[0][0])
    if _sha(_canonical(json.loads(record.decode("utf-8")))) != _sha(record):
        raise Rejected("RECONCILIATION_RECORD_MALFORMED")
    if _revision(bytes(context_bytes), record) != revision_id:
        raise Rejected("RECONCILIATION_REVISION_MISMATCH")

    return {
        "run_id": run_id,
        "replayed": True,
        "reconciliation": json.loads(record.decode("utf-8")),
        "decision_eligibility_asserted": False,
    }
