"""Persisted, evidence-linked audited native decision-run Silver recording.

Records immutable evidence-linked strategy or portfolio-risk decision stages
and exactly replays only stages that actually ran. No eligibility, live
trading, healing, backfill, adoption, or execution authority.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.audited_decision_run import (
    ensure_no_point_in_time_decision,
)
from nse_quant.data_platform.contracts import DatasetContract, Layer, WritePolicy
from nse_quant.data_platform.native_strategy_input_coverage import Rejected
from nse_quant.data_platform.native_strategy_requirements import STRATEGY

VERSION = "native-audited-decision-run-silver-recording@1"
COMMAND = "record.native_audited_decision_run@1"
MAX_CONTEXT_BYTES = 1_048_576
MAX_RECORD_BYTES = 262_144
MAX_JSON_BYTES = 131_072
DOMAIN = (
    "audited_decision_run_versions",
    "audited_decision_run_sets",
    "audited_decision_run_observations",
    "audited_decision_run_attempts",
)
TABLES = {("silver", name) for name in DOMAIN} | {
    ("medallion_audit", name) for name in ("schema_versions", "dataset_contracts", "jobs", "job_events")
}
CONTRACT = DatasetContract(
    "silver.native_audited_decision_run_observations",
    "1",
    Layer.SILVER,
    WritePolicy.APPEND_REVISIONS,
    ("revision_id", "ordinal"),
    (
        "revision_id",
        "ordinal",
        "run_id",
        "stage",
        "source_observation_id",
        "recorded_at",
        "record_bytes",
    ),
    "native_audited_decision_run",
)
DEFINITION = (
    VERSION,
    COMMAND,
    CONTRACT.canonical_json(),
    MAX_CONTEXT_BYTES,
    MAX_RECORD_BYTES,
    MAX_JSON_BYTES,
    "exact evidence-linked immutable strategy or portfolio-risk decision stage",
    "POINT_IN_TIME_DECISION remains rejected",
    "no eligibility, execution authority, healing, backfill, or adoption",
)

_SUPPORTED_STAGES = frozenset({"strategy", "portfolio_risk"})
_NEVER_AUTO_COVERABLE = frozenset({"authoritative_identity_and_time"})


@dataclass(frozen=True)
class AuditedDecisionRunRequest:
    run_id: str
    stage: str
    decision_fingerprint: str
    inputs: dict[str, Any]
    outcome: dict[str, Any]
    evidence_refs: dict[str, str]
    coverage_revision_id: str
    coverage_recording_fingerprint: str

    def __post_init__(self) -> None:
        if type(self.run_id) is not str or not 1 <= len(self.run_id) <= 128:
            raise Rejected("EXACT_RUN_ID_REQUIRED")
        if self.stage not in _SUPPORTED_STAGES:
            raise Rejected("UNSUPPORTED_STAGE")
        if not _pin(self.decision_fingerprint):
            raise Rejected("EXACT_DECISION_FINGERPRINT_REQUIRED")
        if not _pin(self.coverage_revision_id):
            raise Rejected("EXACT_COVERAGE_REVISION_PIN_REQUIRED")
        if not _pin(self.coverage_recording_fingerprint):
            raise Rejected("EXACT_COVERAGE_RECORDING_PIN_REQUIRED")
        if type(self.inputs) is not dict or type(self.outcome) is not dict:
            raise Rejected("EXACT_DECISION_DOCUMENTS_REQUIRED")
        if type(self.evidence_refs) is not dict or not self.evidence_refs:
            raise Rejected("EXACT_EVIDENCE_REFS_REQUIRED")
        if any(
            type(key) is not str or not key or type(value) is not str or not value
            for key, value in self.evidence_refs.items()
        ):
            raise Rejected("EXACT_EVIDENCE_REF_REQUIRED")
        if "authoritative_identity_and_time" in self.evidence_refs:
            raise Rejected("AUTHORITATIVE_IDENTITY_NOT_AUTO_COVERABLE")
        ensure_no_point_in_time_decision(self.outcome)


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


def _json_text(value: dict[str, Any], label: str) -> str:
    raw = _canonical(value)
    if not 0 < len(raw) <= MAX_JSON_BYTES:
        raise Rejected(f"{label}_BYTE_BOUND")
    return raw.decode("utf-8")


def _context(request: AuditedDecisionRunRequest) -> bytes:
    raw = _canonical(
        {
            "version": VERSION,
            "run_id": request.run_id,
            "stage": request.stage,
            "decision_fingerprint": request.decision_fingerprint,
            "inputs": request.inputs,
            "outcome": request.outcome,
            "evidence_refs": request.evidence_refs,
            "coverage_revision_id": request.coverage_revision_id,
            "coverage_recording_fingerprint": request.coverage_recording_fingerprint,
        }
    )
    if not 0 < len(raw) <= MAX_CONTEXT_BYTES:
        raise Rejected("AUDITED_DECISION_RUN_CONTEXT_BYTE_BOUND")
    return raw


def _table(target: Any, name: str) -> str:
    return f"silver.{name}"


def _owned(target: Any, *, complete: bool) -> None:
    paths = target.execute("SELECT path FROM duckdb_databases() WHERE database_name=current_database()").fetchall()
    if len(paths) != 1 or not paths[0][0]:
        raise Rejected("FILE_BACKED_AUDITED_DECISION_RUN_SILVER_REQUIRED")
    rows = target.execute(
        "SELECT table_schema,table_name,table_type FROM information_schema.tables "
        "WHERE table_catalog=current_database() LIMIT 9"
    ).fetchall()
    known = {(schema, table) for schema, table, _kind in rows}
    if known - TABLES or any(kind != "BASE TABLE" for _schema, _table, kind in rows) or (complete and known != TABLES):
        raise Rejected("DEDICATED_AUDITED_DECISION_RUN_SILVER_REQUIRED")


def initialize_audited_decision_run_silver(target: Any) -> None:
    """Initialize an explicitly empty dedicated Silver target."""
    _owned(target, complete=False)
    if target.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_catalog=current_database() LIMIT 1"
    ).fetchone():
        raise Rejected("EMPTY_AUDITED_DECISION_RUN_SILVER_INITIALIZATION_REQUIRED")

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
            "strategy VARCHAR NOT NULL,"
            "coverage_revision_id VARCHAR NOT NULL,"
            "coverage_recording_fingerprint VARCHAR NOT NULL,"
            "context BLOB NOT NULL,"
            "stage_count INTEGER NOT NULL,"
            "first_job_id VARCHAR NOT NULL,"
            "recorded_at TIMESTAMPTZ NOT NULL)"
        )
        target.execute(
            f"CREATE TABLE {observations} ("
            "revision_id VARCHAR NOT NULL,"
            "ordinal INTEGER NOT NULL,"
            "run_id VARCHAR NOT NULL,"
            "stage VARCHAR NOT NULL,"
            "decision_fingerprint VARCHAR NOT NULL,"
            "inputs_json TEXT NOT NULL,"
            "outcome_json TEXT NOT NULL,"
            "evidence_refs_json TEXT NOT NULL,"
            "source_observation_id VARCHAR NOT NULL,"
            "record_bytes BLOB NOT NULL,"
            "recorded_at TIMESTAMPTZ NOT NULL,"
            "PRIMARY KEY(revision_id,ordinal),"
            "UNIQUE(revision_id,run_id,stage))"
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
        raise Rejected("AUDITED_DECISION_RUN_SILVER_DEFINITION_DRIFT")
    if target.execute(
        "SELECT CASE WHEN length(fingerprint)<=64 THEN fingerprint END,"
        "CASE WHEN octet_length(encode(contract_json))<=32768 "
        f"THEN contract_json END FROM {contracts} "
        "WHERE dataset_name=? AND contract_version='1'",
        [CONTRACT.name],
    ).fetchall() != [(CONTRACT.fingerprint, CONTRACT.canonical_json())]:
        raise Rejected("AUDITED_DECISION_RUN_SILVER_CONTRACT_DRIFT")
    if target.execute(f"SELECT version FROM {audit} LIMIT 2").fetchall() != [(1,)]:
        raise Rejected("AUDITED_DECISION_RUN_SILVER_AUDIT_SCHEMA_DRIFT")


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


def record_audited_decision_run(
    target: Any,
    *,
    request: AuditedDecisionRunRequest,
    expected_context_sha256: str,
    actor_id: str,
    code_revision: str,
) -> dict[str, Any]:
    """Record one immutable evidence-linked audited decision stage."""
    if type(request) is not AuditedDecisionRunRequest:
        raise Rejected("TYPED_AUDITED_DECISION_RUN_REQUEST_REQUIRED")
    if not _pin(expected_context_sha256):
        raise Rejected("EXACT_EXPECTED_CONTEXT_PIN_REQUIRED")
    if type(actor_id) is not str or not actor_id:
        raise Rejected("EXACT_ACTOR_REQUIRED")
    if type(code_revision) is not str or not code_revision:
        raise Rejected("EXACT_CODE_REVISION_REQUIRED")

    ensure_no_point_in_time_decision(request.outcome)

    recomputed_decision_fingerprint = _sha(
        _canonical(
            [
                request.stage,
                request.inputs,
                request.outcome,
            ]
        )
    )
    if recomputed_decision_fingerprint != request.decision_fingerprint:
        raise Rejected("DECISION_FINGERPRINT_MISMATCH")
    _schema(target)
    sets = _table(target, DOMAIN[1])
    observations = _table(target, DOMAIN[2])
    attempts = _table(target, DOMAIN[3])
    jobs = "medallion_audit.jobs"

    for table, field, value in (
        (sets, "run_id", request.run_id),
        (attempts, "run_id", request.run_id),
        (jobs, "scope_ref", "sha256:" + request.run_id),
        (observations, "run_id", request.run_id),
    ):
        if target.execute(f'SELECT 1 FROM {table} WHERE "{field}"=? LIMIT 1', [value]).fetchone():
            raise Rejected("AUDITED_DECISION_RUN_FIRST_WRITE_OR_ORPHAN_OBLIGATION")

    context = _context(request)
    if _sha(context) != expected_context_sha256:
        raise Rejected("REVIEWED_AUDITED_DECISION_RUN_CONTEXT_CHANGED")

    inputs_json = _json_text(request.inputs, "INPUTS")
    outcome_json = _json_text(request.outcome, "OUTCOME")
    evidence_refs_json = _json_text(request.evidence_refs, "EVIDENCE_REFS")
    record = _canonical(
        {
            "version": VERSION,
            "run_id": request.run_id,
            "stage": request.stage,
            "decision_fingerprint": request.decision_fingerprint,
            "inputs": request.inputs,
            "outcome": request.outcome,
            "evidence_refs": request.evidence_refs,
        }
    )
    if not 0 < len(record) <= MAX_RECORD_BYTES:
        raise Rejected("AUDITED_DECISION_RUN_RECORD_BYTE_BOUND")

    revision = _revision(context, record)
    ledger = AuditLedger(target)
    config = _sha(_canonical([DEFINITION, expected_context_sha256]))
    job = ledger.plan_job(
        command_name=COMMAND,
        actor_id=actor_id,
        code_revision=code_revision,
        scope_ref="sha256:" + request.run_id,
        config_hash=config,
    )
    with ledger.execution(job):
        target.execute("BEGIN TRANSACTION")
        try:
            target.execute(
                f"INSERT INTO {sets} VALUES (?,?,?,?,?,?,?,?,?)",
                [
                    revision,
                    request.run_id,
                    STRATEGY,
                    request.coverage_revision_id,
                    request.coverage_recording_fingerprint,
                    context,
                    1,
                    job,
                    datetime.now(UTC),
                ],
            )
            target.execute(
                f"INSERT INTO {observations} VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                [
                    revision,
                    0,
                    request.run_id,
                    request.stage,
                    request.decision_fingerprint,
                    inputs_json,
                    outcome_json,
                    evidence_refs_json,
                    request.run_id + ":" + request.stage,
                    record,
                    datetime.now(UTC),
                ],
            )
            target.execute(
                f"INSERT INTO {attempts} VALUES (?,?,?)",
                [job, request.run_id, revision],
            )
            target.execute("COMMIT")
        except BaseException:
            target.execute("ROLLBACK")
            raise

    return {
        "revision_id": revision,
        "recording_fingerprint": _recording_fingerprint(target, revision),
        "stage_count": 1,
        "job_id": job,
        "decision_eligibility_asserted": False,
    }


def _recording_fingerprint(target: Any, revision_id: str) -> str:
    if not _pin(revision_id):
        raise Rejected("EXACT_AUDITED_DECISION_RUN_REVISION_REQUIRED")
    _schema(target)
    sets = _table(target, DOMAIN[1])
    observations = _table(target, DOMAIN[2])
    row = target.execute(
        f"SELECT context,stage_count FROM {sets} WHERE revision_id=? LIMIT 2",
        [revision_id],
    ).fetchall()
    if len(row) != 1:
        raise Rejected("AUDITED_DECISION_RUN_EXACT_SET_REQUIRED")
    context = bytes(row[0][0])
    records = target.execute(
        f"SELECT record_bytes FROM {observations} WHERE revision_id=? ORDER BY ordinal LIMIT ?",
        [revision_id, row[0][1] + 1],
    ).fetchall()
    if len(records) != row[0][1] or not 1 <= len(records) <= 2:
        raise Rejected("AUDITED_DECISION_RUN_RECORD_COVERAGE_MISMATCH")
    return _sha(
        _canonical(
            [
                _sha(_canonical(DEFINITION)),
                _sha(context),
                [_sha(bytes(item[0])) for item in records],
            ]
        )
    )


def replay_audited_decision_run(
    target: Any,
    *,
    run_id: str,
    stage: str,
    expected_revision_id: str,
    expected_recording_fingerprint: str,
) -> dict[str, Any]:
    """Exactly replay one previously recorded executed decision stage."""
    if type(run_id) is not str or not run_id:
        raise Rejected("EXACT_RUN_ID_REQUIRED")
    if stage not in _SUPPORTED_STAGES:
        raise Rejected("UNSUPPORTED_STAGE")
    if not _pin(expected_revision_id):
        raise Rejected("EXACT_REVISION_PIN_REQUIRED")
    if not _pin(expected_recording_fingerprint):
        raise Rejected("EXACT_RECORDING_FINGERPRINT_REQUIRED")

    _schema(target)
    sets = _table(target, DOMAIN[1])
    observations = _table(target, DOMAIN[2])
    row = target.execute(
        f"SELECT revision_id,stage_count FROM {sets} WHERE run_id=? LIMIT 2",
        [run_id],
    ).fetchall()
    if len(row) != 1:
        raise Rejected("AUDITED_DECISION_RUN_EXACT_SET_REQUIRED")
    revision_id, stage_count = row[0]
    if revision_id != expected_revision_id:
        raise Rejected("AUDITED_DECISION_RUN_REVISION_MISMATCH")
    actual = _recording_fingerprint(target, revision_id)
    if actual != expected_recording_fingerprint:
        raise Rejected("AUDITED_DECISION_RUN_RECORDING_FINGERPRINT_CHANGED")

    records = target.execute(
        "SELECT stage,decision_fingerprint,inputs_json,outcome_json,"
        f"evidence_refs_json,record_bytes FROM {observations} "
        "WHERE revision_id=? AND run_id=? AND stage=? LIMIT 2",
        [revision_id, run_id, stage],
    ).fetchall()
    if not records:
        return {
            "run_id": run_id,
            "stage": stage,
            "replayed": False,
            "reason": "STAGE_NOT_EXECUTED",
            "decision_eligibility_asserted": False,
        }
    if len(records) != 1 or stage_count != 1:
        raise Rejected("AUDITED_DECISION_RUN_STAGE_COVERAGE_MISMATCH")

    stage_name, stored, inputs_json, outcome_json, refs_json, record_bytes = records[0]
    inputs = json.loads(inputs_json)
    outcome = json.loads(outcome_json)
    evidence_refs = json.loads(refs_json)
    ensure_no_point_in_time_decision(outcome)
    recomputed = _sha(_canonical([stage_name, inputs, outcome]))
    if recomputed != stored:
        raise Rejected("REPLAY_FINGERPRINT_MISMATCH")
    expected_record = _canonical(
        {
            "version": VERSION,
            "run_id": run_id,
            "stage": stage_name,
            "decision_fingerprint": stored,
            "inputs": inputs,
            "outcome": outcome,
            "evidence_refs": evidence_refs,
        }
    )
    if expected_record != bytes(record_bytes):
        raise Rejected("REPLAY_RECORD_MISMATCH")

    return {
        "run_id": run_id,
        "stage": stage_name,
        "replayed": True,
        "decision_fingerprint": recomputed,
        "evidence_refs": evidence_refs,
        "decision_eligibility_asserted": False,
    }
