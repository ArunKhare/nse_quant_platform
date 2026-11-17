"""Persist independently sourced authoritative identity/time evidence Silver.

Records an immutable evidence bundle for canonical underlying identity,
derivative binding, and authorized revocation. Replays the exact evidence.
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

VERSION = "native-authoritative-identity-time-evidence-silver@1"
COMMAND = "record.native_authoritative_identity_time_evidence@1"
MAX_DOCUMENT_BYTES = 262_144
DOMAIN = (
    "identity_time_evidence_versions",
    "identity_time_evidence_sets",
    "identity_time_evidence_observations",
    "identity_time_evidence_attempts",
)
TABLES = {("silver", name) for name in DOMAIN} | {
    ("medallion_audit", name) for name in ("schema_versions", "dataset_contracts", "jobs", "job_events")
}
CONTRACT = DatasetContract(
    "silver.native_authoritative_identity_time_evidence_observations",
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
    "native_authoritative_identity_time_evidence",
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
    return f"silver.{name}"


def _owned(target: Any, *, complete: bool) -> None:
    paths = target.execute("SELECT path FROM duckdb_databases() WHERE database_name=current_database()").fetchall()
    if len(paths) != 1 or not paths[0][0]:
        raise Rejected("FILE_BACKED_IDENTITY_TIME_EVIDENCE_SILVER_REQUIRED")
    rows = target.execute(
        "SELECT table_schema,table_name,table_type FROM information_schema.tables "
        "WHERE table_catalog=current_database() LIMIT 9"
    ).fetchall()
    known = {(schema, table) for schema, table, _kind in rows}
    if known - TABLES or any(kind != "BASE TABLE" for _s, _t, kind in rows) or (complete and known != TABLES):
        raise Rejected("DEDICATED_IDENTITY_TIME_EVIDENCE_SILVER_REQUIRED")


def initialize_identity_time_evidence_silver(target: Any) -> None:
    """Initialize an explicitly empty dedicated identity/time evidence target."""
    _owned(target, complete=False)
    if target.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_catalog=current_database() LIMIT 1"
    ).fetchone():
        raise Rejected("EMPTY_IDENTITY_TIME_EVIDENCE_INITIALIZATION_REQUIRED")
    AuditLedger(target).initialize()
    versions, sets, observations, attempts = (_table(target, n) for n in DOMAIN)
    target.execute("BEGIN TRANSACTION")
    try:
        target.execute("CREATE SCHEMA silver")
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
    expected = _canonical((VERSION, COMMAND, CONTRACT.canonical_json()))
    if target.execute(
        f"SELECT version,CASE WHEN octet_length(definition)<=32768 THEN definition END FROM {versions} LIMIT 2"
    ).fetchall() != [(1, expected)]:
        raise Rejected("IDENTITY_TIME_EVIDENCE_DEFINITION_DRIFT")


def _validate_evidence(evidence: dict[str, Any]) -> None:
    if type(evidence) is not dict:
        raise Rejected("IDENTITY_TIME_EVIDENCE_DOCUMENT_REQUIRED")
    if evidence.get("version") != VERSION:
        raise Rejected("IDENTITY_TIME_EVIDENCE_VERSION_MISMATCH")
    if evidence.get("strategy") != STRATEGY:
        raise Rejected("IDENTITY_TIME_EVIDENCE_STRATEGY_MISMATCH")
    if evidence.get("point_in_time_decision") is True:
        raise Rejected("POINT_IN_TIME_DECISION")
    if evidence.get("auto_coverable") is not False:
        raise Rejected("IDENTITY_TIME_EVIDENCE_NOT_AUTO_COVERABLE")
    if evidence.get("decision_eligibility_asserted") is not False:
        raise Rejected("IDENTITY_TIME_EVIDENCE_ELIGIBILITY_FORBIDDEN")
    identity = evidence.get("identity")
    if type(identity) is not dict:
        raise Rejected("IDENTITY_TIME_IDENTITY_REQUIRED")
    if identity.get("canonical_underlying") not in ("NIFTY", "BANKNIFTY"):
        raise Rejected("IDENTITY_TIME_CANONICAL_UNDERLYING_INVALID")
    if identity.get("source") != "exchange_master":
        raise Rejected("IDENTITY_TIME_IDENTITY_SOURCE_INVALID")
    if not _pin(identity.get("revision_id")) or not _pin(identity.get("recording_fingerprint")):
        raise Rejected("IDENTITY_TIME_IDENTITY_EVIDENCE_INVALID")
    derivative = evidence.get("derivative")
    if type(derivative) is not dict:
        raise Rejected("IDENTITY_TIME_DERIVATIVE_REQUIRED")
    if derivative.get("binding") != "canonical_underlying_to_derivative":
        raise Rejected("IDENTITY_TIME_DERIVATIVE_BINDING_INVALID")
    if not _pin(derivative.get("revision_id")) or not _pin(derivative.get("recording_fingerprint")):
        raise Rejected("IDENTITY_TIME_DERIVATIVE_EVIDENCE_INVALID")
    revocation = evidence.get("authorized_revocation")
    if type(revocation) is not dict:
        raise Rejected("IDENTITY_TIME_REVOCATION_REQUIRED")
    if revocation.get("authorized") is not True:
        raise Rejected("IDENTITY_TIME_REVOCATION_NOT_AUTHORIZED")
    if not _pin(revocation.get("revision_id")) or not _pin(revocation.get("recording_fingerprint")):
        raise Rejected("IDENTITY_TIME_REVOCATION_EVIDENCE_INVALID")


def evidence_context(evidence: dict[str, Any]) -> str:
    """Return the exact context hash for an identity/time evidence document."""
    _validate_evidence(evidence)
    return _sha(_canonical(evidence))


def _revision(context: bytes, record: bytes) -> str:
    return _sha(
        _canonical(
            [
                _sha(_canonical((VERSION, COMMAND, CONTRACT.canonical_json()))),
                _sha(context),
                _sha(record),
            ]
        )
    )


def record_identity_time_evidence(
    target: Any,
    *,
    evidence: dict[str, Any],
    expected_context_sha256: str,
    actor_id: str,
    code_revision: str,
) -> dict[str, Any]:
    """Record one immutable identity/time evidence bundle."""
    _validate_evidence(evidence)
    if not _pin(expected_context_sha256):
        raise Rejected("EXACT_EXPECTED_CONTEXT_PIN_REQUIRED")
    if type(actor_id) is not str or not actor_id:
        raise Rejected("EXACT_ACTOR_REQUIRED")
    if type(code_revision) is not str or not code_revision:
        raise Rejected("EXACT_CODE_REVISION_REQUIRED")
    context = _canonical(evidence)
    if _sha(context) != expected_context_sha256:
        raise Rejected("REVIEWED_IDENTITY_TIME_EVIDENCE_CONTEXT_CHANGED")
    if not 0 < len(context) <= MAX_DOCUMENT_BYTES:
        raise Rejected("IDENTITY_TIME_EVIDENCE_BYTE_BOUND")
    run_id = evidence["run_id"]
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
            raise Rejected("IDENTITY_TIME_EVIDENCE_FIRST_WRITE_OR_ORPHAN_OBLIGATION")
    revision = _revision(context, context)
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
                f"INSERT INTO {observations} VALUES (?,?,?,?,?,?)",
                [
                    revision,
                    0,
                    run_id,
                    run_id + ":identity_time_evidence",
                    context,
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
        "recording_fingerprint": _sha(context),
        "job_id": job,
        "decision_eligibility_asserted": False,
    }


def replay_identity_time_evidence(
    target: Any,
    *,
    run_id: str,
    expected_revision_id: str,
    expected_recording_fingerprint: str,
) -> dict[str, Any]:
    """Exactly replay a persisted identity/time evidence bundle."""
    if type(run_id) is not str or not run_id:
        raise Rejected("EXACT_RUN_ID_REQUIRED")
    if not _pin(expected_revision_id) or not _pin(expected_recording_fingerprint):
        raise Rejected("EXACT_EVIDENCE_PIN_REQUIRED")
    _schema(target)
    sets = _table(target, DOMAIN[1])
    observations = _table(target, DOMAIN[2])
    row = target.execute(f"SELECT revision_id,context FROM {sets} WHERE run_id=? LIMIT 2", [run_id]).fetchall()
    if len(row) != 1:
        raise Rejected("IDENTITY_TIME_EVIDENCE_EXACT_SET_REQUIRED")
    revision_id, context_bytes = row[0]
    if revision_id != expected_revision_id:
        raise Rejected("IDENTITY_TIME_EVIDENCE_REVISION_MISMATCH")
    context = bytes(context_bytes)
    if _sha(context) != expected_recording_fingerprint:
        raise Rejected("IDENTITY_TIME_EVIDENCE_FINGERPRINT_CHANGED")
    records = target.execute(
        f"SELECT record_bytes FROM {observations} WHERE revision_id=? AND run_id=? LIMIT 2",
        [revision_id, run_id],
    ).fetchall()
    if len(records) != 1 or bytes(records[0][0]) != context:
        raise Rejected("IDENTITY_TIME_EVIDENCE_RECORD_MISMATCH")
    evidence = json.loads(context.decode("utf-8"))
    _validate_evidence(evidence)
    return {
        "run_id": run_id,
        "replayed": True,
        "evidence": evidence,
        "decision_eligibility_asserted": False,
    }
