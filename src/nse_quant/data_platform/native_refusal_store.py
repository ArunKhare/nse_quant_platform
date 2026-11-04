"""Audited first-write native refusal decisions, not admission receipt imports or trading."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nse_quant.data_platform import native_refusal_decision as kernel
from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.native_refusal_service import evaluate_native_refusal

VERSION = "native-prestrategy-refusal-recording@1"
COMMAND = "decide.native_prestrategy_refusal@1"
MAX_JOBS = 256
DEFINITION = kernel.canonical(
    [
        VERSION,
        COMMAND,
        kernel.VERSION,
        "first-write-only per explicit attempt_id; "
        "retain complete decision entry and all audit links",
        "original failed/unlinked obligations never healed by a later attempt",
    ]
)
TABLES = {("native_decisions", n) for n in ("schema_versions", "decisions", "attempts")} | {
    ("medallion_audit", n) for n in ("schema_versions", "dataset_contracts", "jobs", "job_events")
}


def name(conn: Any, schema: str, table: str) -> str:
    row = conn.execute("SELECT current_database()").fetchone()
    if row is None:
        raise kernel.NativeDecisionRejected("DECISION_CATALOG_UNAVAILABLE")
    return ".".join('"' + str(p).replace('"', '""') + '"' for p in (row[0], schema, table))


def _paths(conn: Any) -> set[Path]:
    return {
        Path(row[2]).resolve() for row in conn.execute("PRAGMA database_list").fetchall() if row[2]
    }


def _owned(conn: Any, complete: bool) -> None:
    row = conn.execute("SELECT current_database()").fetchone()
    if row is None or not any(
        r[1] == row[0] and r[2] for r in conn.execute("PRAGMA database_list").fetchall()
    ):
        raise kernel.NativeDecisionRejected("DECISION_FILE_BACKED_TARGET_REQUIRED")
    inventory = conn.execute(
        "SELECT table_schema,table_name,table_type FROM information_schema.tables "
        "WHERE table_catalog=current_database() ORDER BY table_schema,table_name LIMIT 9"
    ).fetchall()
    known = {(s, t) for s, t, _kind in inventory}
    if (
        known - TABLES
        or any(kind != "BASE TABLE" for _s, _t, kind in inventory)
        or (complete and known != TABLES)
    ):
        raise kernel.NativeDecisionRejected("DEDICATED_NATIVE_DECISION_DATABASE_REQUIRED")


def _initialize(conn: Any) -> None:
    _owned(conn, False)
    AuditLedger(conn).initialize()
    schema = name(conn, "native_decisions", "schema_versions")
    decisions = name(conn, "native_decisions", "decisions")
    attempts = name(conn, "native_decisions", "attempts")
    conn.execute("BEGIN TRANSACTION")
    try:
        conn.execute(f"CREATE SCHEMA IF NOT EXISTS {schema.rsplit('.', 1)[0]}")
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS {schema} "
            "(version INTEGER PRIMARY KEY,definition_bytes BLOB NOT NULL)"
        )
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS {decisions} "
            "(decision_id VARCHAR PRIMARY KEY,attempt_key VARCHAR UNIQUE NOT NULL,"
            "entry_bytes BLOB NOT NULL,first_job_id VARCHAR NOT NULL,"
            "recorded_at TIMESTAMPTZ NOT NULL)"
        )
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS {attempts} "
            "(job_id VARCHAR PRIMARY KEY,decision_id VARCHAR NOT NULL,"
            "attempt_key VARCHAR NOT NULL)"
        )
        versions = conn.execute(
            f"SELECT version,CASE WHEN octet_length(definition_bytes)<=32768 "
            f"THEN definition_bytes END FROM {schema} LIMIT 2"
        ).fetchall()
        if versions:
            if versions != [(1, DEFINITION)]:
                raise kernel.NativeDecisionRejected("DECISION_SCHEMA_OR_DEFINITION_MISMATCH")
        else:
            if (
                conn.execute(f"SELECT 1 FROM {decisions} LIMIT 1").fetchone()
                or conn.execute(f"SELECT 1 FROM {attempts} LIMIT 1").fetchone()
            ):
                raise kernel.NativeDecisionRejected("DECISION_PARTIAL_SCHEMA_NOT_ADOPTABLE")
            conn.execute(f"INSERT INTO {schema} VALUES (1,?)", [DEFINITION])
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def _attempt_key(doc: dict[str, Any]) -> str:
    return kernel.sha(kernel.canonical([VERSION, doc["attempt_id"]]))


def _configuration(doc: dict[str, Any], runtime: object) -> str:
    return kernel.sha(kernel.canonical([VERSION, doc, runtime]))


def record_native_refusal(
    publications: Any | None,
    target: Any,
    *,
    request: kernel.RefusalRequest,
    actor_id: str,
    initialize: bool = False,
) -> dict[str, str]:
    """Actual source assessment under audit; no arbitrary prebuilt decision-entry import.

    Source read-only; dedicated target single-owner; no enclosing transactions. No retry,
    adoption, supersession or cleanup. First-write conflict is checked before source reads.
    """
    doc = kernel.request_document(request)
    if (
        type(initialize) is not bool
        or type(actor_id) is not str
        or not 1 <= len(actor_id) <= 128
        or actor_id != actor_id.strip()
        or any(ord(c) < 32 for c in actor_id)
    ):
        raise kernel.NativeDecisionRejected("DECISION_BOUNDED_EXECUTION_IDENTITIES_REQUIRED")
    if publications is target:
        raise kernel.NativeDecisionRejected("SEPARATE_NATIVE_DECISION_DATABASE_REQUIRED")
    _owned(target, not initialize)
    if (
        kernel.admission_may_be_observed(request)
        and publications is not None
        and any(
            a == b or (a.exists() and b.exists() and a.samefile(b))
            for a in _paths(publications)
            for b in _paths(target)
        )
    ):
        raise kernel.NativeDecisionRejected("SEPARATE_NATIVE_DECISION_DATABASE_REQUIRED")
    if initialize:
        _initialize(target)
    _owned(target, True)
    schema = name(target, "native_decisions", "schema_versions")
    if target.execute(
        f"SELECT version,CASE WHEN octet_length(definition_bytes)<=32768 "
        f"THEN definition_bytes END FROM {schema} LIMIT 2"
    ).fetchall() != [(1, DEFINITION)]:
        raise kernel.NativeDecisionRejected("DECISION_SCHEMA_OR_DEFINITION_MISMATCH")
    decisions = name(target, "native_decisions", "decisions")
    attempts = name(target, "native_decisions", "attempts")
    jobs = name(target, "medallion_audit", "jobs")
    key = _attempt_key(doc)
    if target.execute(f"SELECT 1 FROM {decisions} WHERE attempt_key=?", [key]).fetchone():
        raise kernel.NativeDecisionRejected("DECISION_ATTEMPT_FIRST_WRITE_ONLY")
    if target.execute(
        f"SELECT 1 FROM {jobs} WHERE scope_ref=? LIMIT 1",
        ["sha256:" + key],
    ).fetchone():
        raise kernel.NativeDecisionRejected("DECISION_PRIOR_OBLIGATION_REVIEW_REQUIRED")
    ledger = AuditLedger(target)
    job = ledger.plan_job(
        command_name=COMMAND,
        actor_id=actor_id,
        code_revision=request.reviewed_code_revision,
        scope_ref="sha256:" + key,
        config_hash=_configuration(doc, kernel.runtime_context()),
    )
    with ledger.execution(job):
        raw = evaluate_native_refusal(publications, request=request)
        decision_id = kernel.sha(raw)
        replayed = kernel.replay_refusal_entry(raw, expected_decision_id=decision_id)
        if replayed["frozen_input"]["request"] != doc:
            raise kernel.NativeDecisionRejected("DECISION_REQUEST_CHANGED_DURING_EVALUATION")
        target.execute("BEGIN TRANSACTION")
        try:
            target.execute(
                f"INSERT INTO {decisions} VALUES (?,?,?,?,?)",
                [decision_id, key, raw, job, datetime.now(UTC)],
            )
            target.execute(f"INSERT INTO {attempts} VALUES (?,?,?)", [job, decision_id, key])
            target.execute("COMMIT")
        except BaseException:
            target.execute("ROLLBACK")
            raise
    recording = _observe(target, decision_id)
    return dict(
        decision_id=decision_id,
        recording_fingerprint=recording.recording_fingerprint,
        job_id=job,
        status="REFUSED_PRE_STRATEGY",
    )


@dataclass(frozen=True)
class NativeRefusalRecording:
    version: str
    decision_id: str
    entry_bytes: bytes
    recording_fingerprint: str
    original_recording_verified: bool = True
    complete_original_refusal_replayed: bool = True
    decision_eligibility_asserted: bool = False
    complete_strategy_replay_asserted: bool = False
    source_authenticity_asserted: bool = False


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None
    )


def _observe(conn: Any, decision_id: str) -> NativeRefusalRecording:
    _owned(conn, True)
    if not kernel.pin(decision_id):
        raise kernel.NativeDecisionRejected("EXACT_NATIVE_DECISION_ID_REQUIRED")
    decisions = name(conn, "native_decisions", "decisions")
    attempts = name(conn, "native_decisions", "attempts")
    jobs = name(conn, "medallion_audit", "jobs")
    events = name(conn, "medallion_audit", "job_events")
    schema = name(conn, "native_decisions", "schema_versions")
    audit_schema = name(conn, "medallion_audit", "schema_versions")
    conn.execute("BEGIN TRANSACTION")
    try:
        versions = conn.execute(
            f"SELECT version,CASE WHEN octet_length(definition_bytes)<=32768 "
            f"THEN definition_bytes END FROM {schema} LIMIT 2"
        ).fetchall()
        audit = conn.execute(f"SELECT version FROM {audit_schema} LIMIT 2").fetchall()
        row = conn.execute(
            f"SELECT attempt_key,CASE WHEN octet_length(entry_bytes)<=? THEN entry_bytes END,"
            f"CASE WHEN length(first_job_id)<=128 THEN first_job_id END,recorded_at "
            f"FROM {decisions} WHERE decision_id=?",
            [kernel.MAX_BYTES, decision_id],
        ).fetchone()
        if row is None or row[1] is None or not kernel.pin(row[0]) or not _aware(row[3]):
            raise kernel.NativeDecisionRejected("DECISION_RECORD_MISSING_OR_UNBOUNDED")
        scoped = conn.execute(
            "SELECT CASE WHEN length(job_id)<=128 THEN job_id END,"
            "CASE WHEN parent_job_id IS NULL THEN NULL ELSE 'INVALID' END,"
            "CASE WHEN length(command_name)<=128 THEN command_name END,"
            "CASE WHEN length(scope_ref)<=80 THEN scope_ref END,"
            "CASE WHEN length(config_hash)<=64 THEN config_hash END,"
            "CASE WHEN length(actor_id)<=128 THEN actor_id END,"
            "CASE WHEN length(code_revision)<=40 THEN code_revision END,created_at "
            f"FROM {jobs} WHERE scope_ref=? ORDER BY job_id LIMIT ?",
            ["sha256:" + row[0], MAX_JOBS + 1],
        ).fetchall()
        linked = conn.execute(
            f"SELECT CASE WHEN length(job_id)<=128 THEN job_id END,"
            f"CASE WHEN length(decision_id)<=64 THEN decision_id END "
            f"FROM {attempts} WHERE attempt_key=? "
            "ORDER BY job_id LIMIT ?",
            [row[0], MAX_JOBS + 1],
        ).fetchall()
        histories = conn.execute(
            "SELECT CASE WHEN length(e.job_id)<=128 THEN e.job_id END,e.event_index,"
            "CASE WHEN length(e.state)<=32 THEN e.state END,"
            "e.recorded_at,e.reason_code IS NULL "
            f"FROM {events} e JOIN {jobs} j ON j.job_id=e.job_id WHERE j.scope_ref=? "
            "ORDER BY e.job_id,e.event_index LIMIT ?",
            ["sha256:" + row[0], MAX_JOBS * 4 + 1],
        ).fetchall()
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    if versions != [(1, DEFINITION)] or audit != [(1,)]:
        raise kernel.NativeDecisionRejected("DECISION_SCHEMA_OR_DEFINITION_MISMATCH")
    raw = bytes(row[1])
    value = kernel.replay_refusal_entry(raw, expected_decision_id=decision_id)
    frozen = value["frozen_input"]
    doc = frozen["request"]
    if _attempt_key(doc) != row[0]:
        raise kernel.NativeDecisionRejected("DECISION_ATTEMPT_BINDING_MISMATCH")
    if (
        not scoped
        or len(scoped) > MAX_JOBS
        or len(linked) > MAX_JOBS
        or len(histories) > MAX_JOBS * 4
        or row[2] not in {r[0] for r in scoped}
        or {r[0] for r in scoped} != {r[0] for r in linked}
        or any(r[1] != decision_id for r in linked)
    ):
        raise kernel.NativeDecisionRejected("DECISION_ATTEMPT_COVERAGE_REVIEW_REQUIRED")
    for job, parent, command, scope, config, actor, revision, created in scoped:
        if (
            type(job) is not str
            or not job.strip()
            or parent is not None
            or command != COMMAND
            or scope != "sha256:" + row[0]
            or config != _configuration(doc, frozen["runtime"])
            or type(actor) is not str
            or not actor.strip()
            or revision != doc["reviewed_code_revision"]
            or not _aware(created)
        ):
            raise kernel.NativeDecisionRejected("DECISION_ORIGINAL_JOB_IDENTITY_MISMATCH")
        history = [r[1:] for r in histories if r[0] == job]
        if (
            len(history) != 3
            or [r[0] for r in history] != [1, 2, 3]
            or [r[1] for r in history] != ["PLANNED", "RUNNING", "SUCCEEDED"]
            or any(not _aware(r[2]) or r[3] is not True for r in history)
        ):
            raise kernel.NativeDecisionRejected("DECISION_ORIGINAL_AUDIT_NOT_SUCCESSFUL")

    # Pin full observed recording metadata/audits in addition to complete decision replay.
    def encode_time(item: object) -> str:
        if not isinstance(item, datetime) or not _aware(item):
            raise kernel.NativeDecisionRejected("DECISION_AWARE_RECORDING_CLOCK_REQUIRED")
        return item.astimezone(UTC).isoformat()

    fingerprint = kernel.sha(
        json.dumps(
            [
                VERSION,
                decision_id,
                row[0],
                kernel.sha(raw),
                row[2],
                row[3],
                scoped,
                linked,
                histories,
            ],
            default=encode_time,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    )
    return NativeRefusalRecording(VERSION, decision_id, raw, fingerprint)


def read_native_refusal_recording(
    source: Any,
    *,
    decision_id: str,
    expected_recording_fingerprint: str,
) -> NativeRefusalRecording:
    """Owned read-only source, exact reviewed recording pins; no latest/cache/repair."""
    if not kernel.pin(expected_recording_fingerprint):
        raise kernel.NativeDecisionRejected("EXACT_NATIVE_DECISION_RECORDING_PIN_REQUIRED")
    observed = _observe(source, decision_id)
    if observed.recording_fingerprint != expected_recording_fingerprint:
        raise kernel.NativeDecisionRejected("NATIVE_DECISION_RECORDING_FINGERPRINT_CHANGED")
    return observed
