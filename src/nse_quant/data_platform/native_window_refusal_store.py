"""Audited first-write native window-publication refusal decisions; never execution."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from nse_quant.data_platform import native_refusal_store as native
from nse_quant.data_platform import native_window_refusal as kernel
from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.native_window_refusal_service import evaluate_window_refusal

VERSION = "native-window-prestrategy-refusal-recording@1"
COMMAND = "decide.native_window_prestrategy_refusal@1"
DOMAIN = ("window_refusal_versions", "window_refusals", "window_refusal_attempts")
TABLES = {("native_decisions", n) for n in DOMAIN} | {
    ("medallion_audit", n) for n in ("schema_versions", "dataset_contracts", "jobs", "job_events")
}
DEFINITION = kernel.canonical(
    [
        VERSION,
        COMMAND,
        kernel.DEFINITION,
        "first-write per attempt_id; complete entry plus original audit/link recording",
        "no healing/adoption; domain commit and final audit separate; never trading permission",
    ]
)
name = native.name


def _text(column: str, bound: int = 128) -> str:
    return f"CASE WHEN octet_length(encode({column}))<={bound} THEN {column} END"


def _owned(c: Any, *, complete: bool) -> None:
    paths = c.execute(
        "SELECT path FROM duckdb_databases() WHERE database_name=current_database()"
    ).fetchall()
    if len(paths) != 1 or not paths[0][0]:
        raise kernel.Rejected("FILE_BACKED_WINDOW_REFUSAL_TARGET_REQUIRED")
    rows = c.execute(
        "SELECT table_schema,table_name,table_type FROM information_schema.tables "
        "WHERE table_catalog=current_database() ORDER BY table_schema,table_name LIMIT 8"
    ).fetchall()
    known = {(s, t) for s, t, _ in rows}
    if (
        known - TABLES
        or any(kind != "BASE TABLE" for _, _, kind in rows)
        or complete
        and known != TABLES
    ):
        raise kernel.Rejected("DEDICATED_WINDOW_REFUSAL_TARGET_REQUIRED")


def initialize_window_refusal_store(c: Any) -> None:
    _owned(c, complete=False)
    if c.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_catalog=current_database() LIMIT 1"
    ).fetchone():
        raise kernel.Rejected("EMPTY_WINDOW_REFUSAL_TARGET_REQUIRED")
    AuditLedger(c).initialize()
    versions, records, attempts = (name(c, "native_decisions", n) for n in DOMAIN)
    c.execute("BEGIN TRANSACTION")
    try:
        c.execute(f"CREATE SCHEMA {versions.rsplit('.', 1)[0]}")
        c.execute(f"CREATE TABLE {versions} (version INTEGER PRIMARY KEY,definition BLOB NOT NULL)")
        c.execute(f"INSERT INTO {versions} VALUES (1,?)", [DEFINITION])
        c.execute(f"""CREATE TABLE {records} (
            decision_id VARCHAR PRIMARY KEY,attempt_key VARCHAR UNIQUE NOT NULL,
            publication_id VARCHAR NOT NULL,entry_bytes BLOB NOT NULL,
            entry_byte_count INTEGER NOT NULL,failed_stage VARCHAR NOT NULL,status VARCHAR NOT NULL,
            first_job_id VARCHAR NOT NULL,recorded_at TIMESTAMPTZ NOT NULL)""")
        c.execute(f"""CREATE TABLE {attempts} (
            job_id VARCHAR PRIMARY KEY,attempt_key VARCHAR NOT NULL,
            decision_id VARCHAR NOT NULL)""")
        c.execute("COMMIT")
    except BaseException:
        c.execute("ROLLBACK")
        raise


def _schema(c: Any) -> None:
    _owned(c, complete=True)
    if c.execute(
        f"SELECT version,CASE WHEN octet_length(definition)<=32768 THEN definition END "
        f"FROM {name(c, 'native_decisions', DOMAIN[0])} LIMIT 2"
    ).fetchall() != [(1, DEFINITION)]:
        raise kernel.Rejected("WINDOW_REFUSAL_SCHEMA_OR_DEFINITION_DRIFT")
    if c.execute(
        f"SELECT version FROM {name(c, 'medallion_audit', 'schema_versions')} LIMIT 2"
    ).fetchall() != [(1,)]:
        raise kernel.Rejected("WINDOW_REFUSAL_AUDIT_SCHEMA_DRIFT")


def attempt_key(doc: dict[str, Any]) -> str:
    return kernel.sha(kernel.canonical([VERSION, doc["attempt_id"]]))


def _config(doc: dict[str, Any], runtime: object) -> str:
    return kernel.sha(kernel.canonical([DEFINITION.hex(), doc, runtime]))


def _unused(c: Any, key: str) -> None:
    for n in DOMAIN[1:]:
        if c.execute(
            f"SELECT 1 FROM {name(c, 'native_decisions', n)} WHERE attempt_key=? LIMIT 1", [key]
        ).fetchone():
            raise kernel.Rejected("WINDOW_REFUSAL_FIRST_WRITE_OR_ORPHAN_OBLIGATION")
    if c.execute(
        f"SELECT 1 FROM {name(c, 'medallion_audit', 'jobs')} WHERE scope_ref=? LIMIT 1",
        ["sha256:" + key],
    ).fetchone():
        raise kernel.Rejected("WINDOW_REFUSAL_FIRST_WRITE_ORIGINAL_AUDIT_OBLIGATION")


def _separate(source: Any, target: Any) -> None:
    if source is target or any(
        a == b or a.samefile(b) for a in native._paths(source) for b in native._paths(target)
    ):
        raise kernel.Rejected("SEPARATE_WINDOW_REFUSAL_DATABASE_REQUIRED")


def record_window_refusal(
    publications: Any | None, target: Any, *, request: kernel.RefusalRequest, actor_id: str
) -> dict[str, Any]:
    """Actual source assessment under native audit. No caller prebuilt-entry import.

    Early refusal never probes the supplied source, including its paths/catalog.
    An operational source failure is a failed job, not a fabricated domain refusal.
    """
    doc = kernel.common.request_document(request)
    if (
        type(actor_id) is not str
        or not 1 <= len(actor_id.encode()) <= 128
        or actor_id != actor_id.strip()
        or any(ord(c) < 32 for c in actor_id)
    ):
        raise kernel.Rejected("EXPLICIT_WINDOW_REFUSAL_ACTOR_REQUIRED")
    _schema(target)
    key = attempt_key(doc)
    _unused(target, key)
    if kernel.common.admission_may_be_observed(request) and publications is not None:
        _separate(publications, target)
    runtime = kernel.runtime_context()
    ledger = AuditLedger(target)
    job = ledger.plan_job(
        command_name=COMMAND,
        actor_id=actor_id,
        code_revision=request.reviewed_code_revision,
        scope_ref="sha256:" + key,
        config_hash=_config(doc, runtime),
    )
    with ledger.execution(job):
        raw = evaluate_window_refusal(publications, request=request)
        decision_id = kernel.sha(raw)
        replayed = kernel.replay_window_refusal_entry(raw, expected_decision_id=decision_id)
        if (
            replayed["frozen_input"]["request"] != doc
            or replayed["frozen_input"]["runtime"] != runtime
        ):
            raise kernel.Rejected("WINDOW_REFUSAL_REQUEST_OR_RUNTIME_CHANGED")
        result = replayed["result"]
        target.execute("BEGIN TRANSACTION")
        try:
            target.execute(
                f"INSERT INTO {name(target, 'native_decisions', DOMAIN[1])} "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                [
                    decision_id,
                    key,
                    request.publication_id,
                    raw,
                    len(raw),
                    result["failed_stage"],
                    result["status"],
                    job,
                    datetime.now(UTC),
                ],
            )
            target.execute(
                f"INSERT INTO {name(target, 'native_decisions', DOMAIN[2])} VALUES (?,?,?)",
                [job, key, decision_id],
            )
            target.execute("COMMIT")
        except BaseException:
            target.execute("ROLLBACK")
            raise
    result_recording = _recording(target, decision_id)
    return dict(
        decision_id=decision_id,
        recording_fingerprint=result_recording.recording_fingerprint,
        job_id=job,
        status="REFUSED_PRE_STRATEGY",
        decision_eligibility_asserted=False,
    )


@dataclass(frozen=True)
class WindowRefusalRecording:
    version: str
    decision_id: str
    recording_fingerprint: str
    entry_bytes: bytes
    original_recording_verified: bool = True
    complete_original_refusal_replayed: bool = True
    current_publication_checked: bool = False
    decision_eligibility_asserted: bool = False
    complete_strategy_replay_asserted: bool = False
    source_authenticity_asserted: bool = False


def _recording(c: Any, decision_id: str) -> WindowRefusalRecording:
    if not kernel.pin(decision_id):
        raise kernel.Rejected("EXACT_WINDOW_REFUSAL_ID_REQUIRED")
    c.execute("BEGIN TRANSACTION")
    try:
        _schema(c)
        table = name(c, "native_decisions", DOMAIN[1])
        head = c.execute(
            f"SELECT {_text('attempt_key', 64)} FROM {table} WHERE decision_id=?", [decision_id]
        ).fetchone()
        if head is None or not kernel.pin(head[0]):
            raise kernel.Rejected("WINDOW_REFUSAL_RECORD_MISSING_OR_ATTEMPT_BOUND")
        key = head[0]
        budget = c.execute(
            f"SELECT count(*),coalesce(sum(octet_length(entry_bytes)),0) FROM {table} "
            "WHERE decision_id=? OR attempt_key=?",
            [decision_id, key],
        ).fetchone()
        if budget is None or budget[0] != 1 or not 1 <= budget[1] <= kernel.MAX_BYTES:
            raise kernel.Rejected("WINDOW_REFUSAL_COVERAGE_OR_AGGREGATE_BYTE_BOUND")
        row = c.execute(
            f"SELECT {_text('publication_id', 64)},CASE WHEN octet_length(entry_bytes)<=? "
            f"THEN entry_bytes END,entry_byte_count,{_text('failed_stage', 64)},"
            f"{_text('status', 64)},{_text('first_job_id')},recorded_at "
            f"FROM {table} WHERE decision_id=?",
            [kernel.MAX_BYTES, decision_id],
        ).fetchone()
        if row is None or any(row[i] is None for i in (0, 1, 3, 4, 5)):
            raise kernel.Rejected("WINDOW_REFUSAL_COMPONENT_TRANSFER_BOUND")
        links = c.execute(
            f"SELECT {_text('job_id')},{_text('attempt_key', 64)},{_text('decision_id', 64)} "
            f"FROM {name(c, 'native_decisions', DOMAIN[2])} "
            "WHERE attempt_key=? OR decision_id=? OR job_id=? LIMIT 3",
            [key, decision_id, row[5]],
        ).fetchall()
        jobs = c.execute(
            f"SELECT {_text('job_id')},{_text('parent_job_id')},{_text('command_name')},"
            f"{_text('actor_id')},{_text('scope_ref', 71)},{_text('code_revision', 40)},"
            f"{_text('config_hash', 64)},created_at FROM {name(c, 'medallion_audit', 'jobs')} "
            "WHERE scope_ref=? OR job_id=? LIMIT 3",
            ["sha256:" + key, row[5]],
        ).fetchall()
        history = c.execute(
            "SELECT event_index,CASE WHEN length(state)<=32 THEN state END,recorded_at,"
            "CASE WHEN reason_code IS NULL OR octet_length(encode(reason_code))<=64 "
            "THEN reason_code ELSE 'INVALID!' END "
            f"FROM {name(c, 'medallion_audit', 'job_events')} "
            "WHERE job_id=? ORDER BY event_index LIMIT 4",
            [row[5]],
        ).fetchall()
        c.execute("COMMIT")
    except BaseException:
        c.execute("ROLLBACK")
        raise
    raw = bytes(row[1])
    replayed = kernel.replay_window_refusal_entry(raw, expected_decision_id=decision_id)
    frozen, result = replayed["frozen_input"], replayed["result"]
    doc = frozen["request"]
    if (
        attempt_key(doc) != key
        or row[:1] != (doc["publication_id"],)
        or row[2:5] != (len(raw), result["failed_stage"], result["status"])
        or links != [(row[5], key, decision_id)]
        or len(jobs) != 1
    ):
        raise kernel.Rejected("WINDOW_REFUSAL_COMPLETE_CONTENT_OR_ORIGINAL_LINK_MISMATCH")
    job = jobs[0]
    if (
        job[:3] != (row[5], None, COMMAND)
        or type(job[3]) is not str
        or not job[3].strip()
        or job[4] != "sha256:" + key
        or job[5] != doc["reviewed_code_revision"]
        or job[6] != _config(doc, frozen["runtime"])
        or [(h[0], h[1], h[3]) for h in history]
        != [(1, "PLANNED", None), (2, "RUNNING", None), (3, "SUCCEEDED", None)]
    ):
        raise kernel.Rejected("WINDOW_REFUSAL_ORIGINAL_AUDIT_NOT_VERIFIED")
    kernel.common.clock(row[6])
    kernel.common.clock(job[7])
    for h in history:
        kernel.common.clock(h[2])

    def default(value: object) -> str:
        if not isinstance(value, datetime):
            raise kernel.Rejected("WINDOW_REFUSAL_RECORDING_METADATA_TYPE")
        return kernel.common.clock(value)

    fingerprint = kernel.sha(
        json.dumps(
            [VERSION, decision_id, key, row[0], kernel.sha(raw), *row[2:], links, jobs, history],
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
            default=default,
        ).encode()
    )
    return WindowRefusalRecording(VERSION, decision_id, fingerprint, raw)


def read_window_refusal_recording(
    c: Any, *, decision_id: str, expected_recording_fingerprint: str
) -> WindowRefusalRecording:
    if not kernel.pin(expected_recording_fingerprint):
        raise kernel.Rejected("EXACT_WINDOW_REFUSAL_RECORDING_PIN_REQUIRED")
    if c.execute(
        "SELECT readonly FROM duckdb_databases() WHERE database_name=current_database()"
    ).fetchall() != [(True,)]:
        raise kernel.Rejected("READONLY_WINDOW_REFUSAL_RECORDING_REQUIRED")
    result = _recording(c, decision_id)
    if result.recording_fingerprint != expected_recording_fingerprint:
        raise kernel.Rejected("WINDOW_REFUSAL_RECORDING_FINGERPRINT_CHANGED")
    return result


def revalidate_window_refusal(
    publications: Any | None, records: Any, *, decision_id: str, expected_recording_fingerprint: str
) -> dict[str, object]:
    """Re-run only original supported refusal stages; no current upstream or strategy claim."""
    args = dict(
        decision_id=decision_id, expected_recording_fingerprint=expected_recording_fingerprint
    )
    before = read_window_refusal_recording(records, **args)
    entry = kernel.replay_window_refusal_entry(before.entry_bytes, expected_decision_id=decision_id)
    request = kernel.request_from_document(entry["frozen_input"]["request"])
    if entry["result"]["admission_observed"] and publications is not None:
        _separate(publications, records)
    fresh = evaluate_window_refusal(publications, request=request)
    after = read_window_refusal_recording(records, **args)
    if before != after or fresh != before.entry_bytes:
        raise kernel.Rejected("WINDOW_REFUSAL_CURRENT_OBSERVATION_DRIFT")
    return dict(
        status="MATCHED_CURRENT_REFUSAL",
        decision_id=decision_id,
        recording_fingerprint=before.recording_fingerprint,
        current_publication_checked=entry["result"]["admission_observed"],
        current_native_upstream_checked=False,
        decision_eligibility_asserted=False,
        complete_strategy_replay_asserted=False,
    )
