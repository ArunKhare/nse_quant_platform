"""Versioned Gold publication candidate for native iron-condor decisions.

Consolidates validated Silver reconciliation, authoritative identity/time
evidence, availability/economic-validity evidence, and coverage evidence-link
context into one immutable, replayable Gold decision artifact. This is a
publication candidate only: no eligibility, live trading, healing, backfill,
adoption, or execution authority. POINT_IN_TIME_DECISION remains rejected.
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

VERSION = "native-iron-condor-decision-gold@1"
COMMAND = "publish.native_iron_condor_decision_gold@1"
MAX_DOCUMENT_BYTES = 262_144
DOMAIN = (
    "decision_gold_versions",
    "decision_gold_sets",
    "decision_gold_observations",
    "decision_gold_attempts",
)
TABLES = {("gold", name) for name in DOMAIN} | {
    ("medallion_audit", name) for name in ("schema_versions", "dataset_contracts", "jobs", "job_events")
}
CONTRACT = DatasetContract(
    "gold.native_iron_condor_decision_observations",
    "1",
    Layer.GOLD,
    WritePolicy.VERSIONED_BUILDS,
    ("build_id", "ordinal"),
    (
        "build_id",
        "ordinal",
        "run_id",
        "source_observation_id",
        "recorded_at",
        "record_bytes",
        "event_ts",
        "published_at",
        "feature_version",
    ),
    "native_iron_condor_decision_gold",
)


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


def _pin(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _table(target: Any, name: str) -> str:
    return f"gold.{name}"


def _owned(target: Any, *, complete: bool) -> None:
    paths = target.execute("SELECT path FROM duckdb_databases() WHERE database_name=current_database()").fetchall()
    if len(paths) != 1 or not paths[0][0]:
        raise Rejected("FILE_BACKED_DECISION_GOLD_REQUIRED")
    rows = target.execute(
        "SELECT table_schema,table_name,table_type FROM information_schema.tables "
        "WHERE table_catalog=current_database() LIMIT 9"
    ).fetchall()
    known = {(schema, table) for schema, table, _kind in rows}
    if known - TABLES or any(kind != "BASE TABLE" for _s, _t, kind in rows) or (complete and known != TABLES):
        raise Rejected("DEDICATED_DECISION_GOLD_REQUIRED")


def initialize_decision_gold(target: Any) -> None:
    """Initialize an explicitly empty dedicated decision Gold target."""
    _owned(target, complete=False)
    if target.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_catalog=current_database() LIMIT 1"
    ).fetchone():
        raise Rejected("EMPTY_DECISION_GOLD_INITIALIZATION_REQUIRED")
    AuditLedger(target).initialize()
    versions, sets, observations, attempts = (_table(target, n) for n in DOMAIN)
    target.execute("BEGIN TRANSACTION")
    try:
        target.execute("CREATE SCHEMA gold")
        target.execute(f"CREATE TABLE {versions} (version INTEGER PRIMARY KEY,definition BLOB NOT NULL)")
        target.execute(
            f"INSERT INTO {versions} VALUES (1,?)",
            [_canonical((VERSION, COMMAND, CONTRACT.canonical_json()))],
        )
        target.execute(
            f"CREATE TABLE {sets} ("
            "revision_id VARCHAR PRIMARY KEY,"
            "run_id VARCHAR NOT NULL,"
            "context BLOB NOT NULL,"
            "first_job_id VARCHAR NOT NULL,"
            "recorded_at TIMESTAMPTZ NOT NULL)"
        )
        target.execute(
            f"CREATE TABLE {observations} ("
            "build_id VARCHAR NOT NULL,"
            "ordinal INTEGER NOT NULL,"
            "run_id VARCHAR NOT NULL,"
            "source_observation_id VARCHAR NOT NULL,"
            "record_bytes BLOB NOT NULL,"
            "recorded_at TIMESTAMPTZ NOT NULL,"
            "event_ts TIMESTAMPTZ NOT NULL,"
            "published_at TIMESTAMPTZ NOT NULL,"
            "feature_version VARCHAR NOT NULL,"
            "PRIMARY KEY(build_id,ordinal),"
            "UNIQUE(build_id,run_id))"
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
    expected = _canonical((VERSION, COMMAND, CONTRACT.canonical_json()))
    if target.execute(
        f"SELECT version,CASE WHEN octet_length(definition)<=32768 THEN definition END FROM {versions} LIMIT 2"
    ).fetchall() != [(1, expected)]:
        raise Rejected("DECISION_GOLD_DEFINITION_DRIFT")


def _validate_gold(document: dict[str, Any]) -> None:
    if type(document) is not dict:
        raise Rejected("DECISION_GOLD_DOCUMENT_REQUIRED")
    if document.get("version") != VERSION:
        raise Rejected("DECISION_GOLD_VERSION_MISMATCH")
    if document.get("strategy") != STRATEGY:
        raise Rejected("DECISION_GOLD_STRATEGY_MISMATCH")
    if document.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if document.get("decision_eligibility_asserted") is not False:
        raise Rejected("DECISION_GOLD_ELIGIBILITY_FORBIDDEN")
    if document.get("complete") is True:
        raise Rejected("DECISION_GOLD_COMPLETION_NOT_ASSERTABLE")
    for field in (
        "reconciliation_revision_id",
        "reconciliation_recording_fingerprint",
        "identity_time_evidence_revision_id",
        "identity_time_evidence_recording_fingerprint",
        "availability_economic_evidence_revision_id",
        "availability_economic_evidence_recording_fingerprint",
        "coverage_revision_id",
        "coverage_recording_fingerprint",
        "coverage_evidence_links_context",
        "authoritative_boundary_context",
    ):
        value = document.get(field)
        if field.endswith("_context"):
            if type(value) is not str or not value:
                raise Rejected(f"DECISION_GOLD_{field.upper()}_REQUIRED")
        elif not _pin(value):
            raise Rejected(f"DECISION_GOLD_{field.upper()}_INVALID")
    stages = document.get("stages")
    if type(stages) is not list or len(stages) != 2:
        raise Rejected("DECISION_GOLD_STAGES_REQUIRED")
    for stage in stages:
        if type(stage) is not dict:
            raise Rejected("DECISION_GOLD_STAGE_DOCUMENT_REQUIRED")
        if stage.get("replayed") is not True:
            raise Rejected("DECISION_GOLD_STAGE_REPLAY_INCOMPLETE")
        if stage.get("decision_eligibility_asserted") is not False:
            raise Rejected("DECISION_GOLD_STAGE_ELIGIBILITY_FORBIDDEN")
        if not _pin(stage.get("revision_id")) or not _pin(stage.get("recording_fingerprint")):
            raise Rejected("DECISION_GOLD_STAGE_EVIDENCE_INVALID")


def gold_context(document: dict[str, Any]) -> str:
    """Return the exact context hash for a Gold decision document."""
    _validate_gold(document)
    return _sha(_canonical(document))


def _revision(context: bytes) -> str:
    return _sha(
        _canonical(
            [
                _sha(_canonical((VERSION, COMMAND, CONTRACT.canonical_json()))),
                _sha(context),
            ]
        )
    )


def publish_decision_gold(
    target: Any,
    *,
    document: dict[str, Any],
    expected_context_sha256: str,
    actor_id: str,
    code_revision: str,
) -> dict[str, Any]:
    """Publish one immutable Gold decision candidate."""
    _validate_gold(document)
    if not _pin(expected_context_sha256):
        raise Rejected("EXACT_EXPECTED_CONTEXT_PIN_REQUIRED")
    if type(actor_id) is not str or not actor_id:
        raise Rejected("EXACT_ACTOR_REQUIRED")
    if type(code_revision) is not str or not code_revision:
        raise Rejected("EXACT_CODE_REVISION_REQUIRED")
    context = _canonical(document)
    if _sha(context) != expected_context_sha256:
        raise Rejected("REVIEWED_DECISION_GOLD_CONTEXT_CHANGED")
    if not 0 < len(context) <= MAX_DOCUMENT_BYTES:
        raise Rejected("DECISION_GOLD_BYTE_BOUND")
    run_id = document["run_id"]
    _schema(target)
    sets = _table(target, DOMAIN[1])
    observations = _table(target, DOMAIN[2])
    attempts = _table(target, DOMAIN[3])
    for table, field, value in (
        (sets, "run_id", run_id),
        (attempts, "run_id", run_id),
        (observations, "run_id", run_id),
    ):
        if target.execute(f'SELECT 1 FROM {table} WHERE "{field}"=? LIMIT 1', [value]).fetchone():
            raise Rejected("DECISION_GOLD_FIRST_WRITE_OR_ORPHAN_OBLIGATION")
    revision = _revision(context)
    ledger = AuditLedger(target)
    job = ledger.plan_job(
        command_name=COMMAND,
        actor_id=actor_id,
        code_revision=code_revision,
        scope_ref="sha256:" + run_id,
        config_hash=_sha(_canonical([expected_context_sha256])),
    )
    with ledger.execution(job):
        target.execute("BEGIN TRANSACTION")
        try:
            target.execute(
                f"INSERT INTO {sets} VALUES (?,?,?,?,?)",
                [revision, run_id, context, job, datetime.now(UTC)],
            )
            target.execute(
                f"INSERT INTO {observations} VALUES (?,?,?,?,?,?,?,?,?)",
                [
                    revision,
                    0,
                    run_id,
                    run_id + ":decision_gold",
                    context,
                    datetime.now(UTC),
                    datetime.now(UTC),
                    datetime.now(UTC),
                    VERSION,
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
        "recording_fingerprint": _sha(context),
        "job_id": job,
        "decision_eligibility_asserted": False,
    }


def replay_decision_gold(
    target: Any,
    *,
    run_id: str,
    expected_revision_id: str,
    expected_recording_fingerprint: str,
) -> dict[str, Any]:
    """Exactly replay a persisted Gold decision candidate."""
    if type(run_id) is not str or not run_id:
        raise Rejected("EXACT_RUN_ID_REQUIRED")
    if not _pin(expected_revision_id) or not _pin(expected_recording_fingerprint):
        raise Rejected("EXACT_GOLD_PIN_REQUIRED")
    _schema(target)
    sets = _table(target, DOMAIN[1])
    observations = _table(target, DOMAIN[2])
    row = target.execute(f"SELECT revision_id,context FROM {sets} WHERE run_id=? LIMIT 2", [run_id]).fetchall()
    if len(row) != 1:
        raise Rejected("DECISION_GOLD_EXACT_SET_REQUIRED")
    revision_id, context_bytes = row[0]
    if revision_id != expected_revision_id:
        raise Rejected("DECISION_GOLD_REVISION_MISMATCH")
    context = bytes(context_bytes)
    if _sha(context) != expected_recording_fingerprint:
        raise Rejected("DECISION_GOLD_FINGERPRINT_CHANGED")
    records = target.execute(
        f"SELECT record_bytes FROM {observations} WHERE build_id=? AND run_id=? LIMIT 2",
        [revision_id, run_id],
    ).fetchall()
    if len(records) != 1 or bytes(records[0][0]) != context:
        raise Rejected("DECISION_GOLD_RECORD_MISMATCH")
    document = json.loads(context.decode("utf-8"))
    _validate_gold(document)
    return {
        "run_id": run_id,
        "replayed": True,
        "gold": document,
        "decision_eligibility_asserted": False,
    }
