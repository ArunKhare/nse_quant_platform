"""Audited append-only local policy checkpoints on a dedicated owned DuckDB file."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from nse_quant.data_platform.policy_checkpoint_record import (
    CheckpointRecord,
    canonical,
    pin,
    series_id,
    sha,
    validate_extension,
)

if TYPE_CHECKING:
    from nse_quant.data_platform.policy_window import PolicyPosition
    from nse_quant.data_platform.signed_policy_window import SignedPolicyInput
    from nse_quant.data_platform.statement_scope_policy import ScopeQuery

VERSION = "audited-policy-checkpoint-store@1"
COMMAND = "record.policy_checkpoint@1"
MAX_RECORDS = 256
MAX_JOBS = 1000
DEFINITION = canonical([VERSION, COMMAND, MAX_RECORDS, MAX_JOBS, "append-only-CAS@1"])


class CheckpointReviewRequired(ValueError):
    """History or audit cannot support a current local checkpoint."""


@dataclass(frozen=True)
class CheckpointView:
    series_id: str
    head: CheckpointRecord | None
    checkpoint_ids: tuple[str, ...]
    evidence_fingerprint: str
    policy_currentness_verified: bool = False
    policy_authority_authenticated: bool = False
    issuer_authenticated: bool = False
    identity_verified: bool = False
    decision_eligibility_asserted: bool = False


def _name(conn: Any, schema: str, table: str) -> str:
    current = conn.execute("SELECT current_database()").fetchone()[0]
    return ".".join('"' + str(x).replace('"', '""') + '"' for x in (current, schema, table))


def _owned(conn: Any) -> None:
    current = conn.execute("SELECT current_database()").fetchone()[0]
    databases = conn.execute("PRAGMA database_list").fetchall()
    if not any(row[1] == current and row[2] for row in databases):
        raise ValueError("FILE_BACKED_CHECKPOINT_DATABASE_REQUIRED")
    tables = conn.execute(
        "SELECT table_schema,table_name FROM information_schema.tables "
        "WHERE table_catalog=current_database()"
    ).fetchall()
    allowed = {
        ("policy_checkpoint", "schema_versions"),
        ("policy_checkpoint", "records"),
        ("policy_checkpoint", "attempts"),
        ("policy_checkpoint", "definitions"),
        ("medallion_audit", "schema_versions"),
        ("medallion_audit", "dataset_contracts"),
        ("medallion_audit", "jobs"),
        ("medallion_audit", "job_events"),
    }
    if any(tuple(row) not in allowed for row in tables):
        raise ValueError("DEDICATED_CHECKPOINT_DATABASE_REQUIRED")


def initialize_policy_checkpoints(conn: Any) -> None:
    from nse_quant.data_platform.audit import AuditLedger

    _owned(conn)
    AuditLedger(conn).initialize()
    conn.execute("BEGIN TRANSACTION")
    try:
        conn.execute('CREATE SCHEMA IF NOT EXISTS "policy_checkpoint"')
        versions = _name(conn, "policy_checkpoint", "schema_versions")
        conn.execute(f"CREATE TABLE IF NOT EXISTS {versions} (version INTEGER PRIMARY KEY)")
        found = conn.execute(f"SELECT version FROM {versions} LIMIT 2").fetchall()
        if found and found != [(1,)]:
            raise ValueError("CHECKPOINT_SCHEMA_VERSION_NOT_SUPPORTED")
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS {_name(conn, 'policy_checkpoint', 'records')} ("
            "checkpoint_id VARCHAR PRIMARY KEY,series_id VARCHAR NOT NULL,"
            "record_json VARCHAR NOT NULL,first_job_id VARCHAR NOT NULL,"
            "recorded_at TIMESTAMPTZ NOT NULL)"
        )
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS {_name(conn, 'policy_checkpoint', 'attempts')} ("
            "job_id VARCHAR PRIMARY KEY,series_id VARCHAR NOT NULL,"
            "checkpoint_id VARCHAR NOT NULL)"
        )
        definitions = _name(conn, "policy_checkpoint", "definitions")
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS {definitions} (version INTEGER PRIMARY KEY,"
            "definition_json VARCHAR NOT NULL)"
        )
        known = conn.execute(
            f"SELECT version,definition_json FROM {definitions} LIMIT 2"
        ).fetchall()
        if found:
            if known != [(1, DEFINITION)]:
                raise ValueError("CHECKPOINT_DEFINITION_NOT_ADOPTABLE")
        else:
            nonempty = any(
                conn.execute(
                    f"SELECT 1 FROM {_name(conn, 'policy_checkpoint', table)} LIMIT 1"
                ).fetchone()
                for table in ("records", "attempts")
            )
            if known or nonempty:
                raise ValueError("CHECKPOINT_PARTIAL_SCHEMA_NOT_ADOPTABLE")
            conn.execute(f"INSERT INTO {definitions} VALUES (1,?)", [DEFINITION])
            conn.execute(f"INSERT INTO {versions} VALUES (1)")
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def _snapshot(conn: Any, scope: str, active_job: str | None = None) -> CheckpointView:
    _owned(conn)
    for schema in ("policy_checkpoint", "medallion_audit"):
        if conn.execute(
            f"SELECT version FROM {_name(conn, schema, 'schema_versions')} LIMIT 2"
        ).fetchall() != [(1,)]:
            raise CheckpointReviewRequired("CHECKPOINT_SCHEMA_NOT_SUPPORTED")
    if conn.execute(
        f"SELECT version,definition_json FROM "
        f"{_name(conn, 'policy_checkpoint', 'definitions')} LIMIT 2"
    ).fetchall() != [(1, DEFINITION)]:
        raise CheckpointReviewRequired("CHECKPOINT_DEFINITION_MISMATCH")
    records = conn.execute(
        f"SELECT checkpoint_id,series_id,"
        f"CASE WHEN octet_length(encode(record_json))<=16384 THEN record_json END,"
        f"first_job_id,recorded_at FROM {_name(conn, 'policy_checkpoint', 'records')} "
        "WHERE series_id=? LIMIT ?",
        [scope, MAX_RECORDS + 1],
    ).fetchall()
    attempts = conn.execute(
        f"SELECT job_id,checkpoint_id FROM {_name(conn, 'policy_checkpoint', 'attempts')} "
        "WHERE series_id=? ORDER BY job_id LIMIT ?",
        [scope, MAX_JOBS + 1],
    ).fetchall()
    jobs = conn.execute(
        f"SELECT job_id,parent_job_id,command_name,config_hash,created_at,actor_id,code_revision "
        f"FROM {_name(conn, 'medallion_audit', 'jobs')} WHERE scope_ref=? "
        "ORDER BY job_id LIMIT ?",
        [scope, MAX_JOBS + 1],
    ).fetchall()
    if len(records) > MAX_RECORDS or len(attempts) > MAX_JOBS or len(jobs) > MAX_JOBS:
        raise CheckpointReviewRequired("CHECKPOINT_HISTORY_CAPACITY")
    decoded: dict[str, CheckpointRecord] = {}
    origins: dict[str, str] = {}
    for key, stored_scope, raw, origin, clock in records:
        if (
            not isinstance(raw, str)
            or not isinstance(clock, datetime)
            or clock.tzinfo is None
            or clock.utcoffset() is None
        ):
            raise CheckpointReviewRequired("CHECKPOINT_RECORD_CLOCK_OR_SIZE_INVALID")
        try:
            value = json.loads(raw)
            if not isinstance(value, dict) or canonical(value) != raw:
                raise CheckpointReviewRequired("CHECKPOINT_CANONICAL_RECORD_REQUIRED")
            if not isinstance(value.get("denied_keys"), list):
                raise CheckpointReviewRequired("CHECKPOINT_DENIAL_LIST_REQUIRED")
            value["denied_keys"] = tuple(value["denied_keys"])
            item = CheckpointRecord(**value)
        except CheckpointReviewRequired:
            raise
        except (ValueError, TypeError, KeyError, RecursionError):
            raise CheckpointReviewRequired("CHECKPOINT_RECORD_NOT_VALID") from None
        if key != item.checkpoint_id or stored_scope != item.series_id or item.series_id != scope:
            raise CheckpointReviewRequired("CHECKPOINT_RECORD_HASH_OR_SCOPE_MISMATCH")
        decoded[key], origins[key] = item, origin
    ordered: list[CheckpointRecord] = []
    remaining = dict(decoded)
    head = None
    while remaining:
        children = [
            item
            for item in remaining.values()
            if item.previous_id == (head.checkpoint_id if head else None)
        ]
        if len(children) != 1:
            raise CheckpointReviewRequired("CHECKPOINT_FORK_OR_UNLINKED_HISTORY")
        candidate = children[0]
        validate_extension(head, candidate)
        ordered.append(candidate)
        remaining.pop(candidate.checkpoint_id)
        head = candidate
    linked = dict(attempts)
    if len(linked) != len(attempts) or any(key not in decoded for key in linked.values()):
        raise CheckpointReviewRequired("CHECKPOINT_ATTEMPT_LINK_INVALID")
    audit_rows: list[object] = []
    for job, parent, command, config, clock, actor, revision in jobs:
        events = conn.execute(
            f"SELECT event_index,state,recorded_at,reason_code "
            f"FROM {_name(conn, 'medallion_audit', 'job_events')} WHERE job_id=? "
            "ORDER BY event_index LIMIT 7",
            [job],
        ).fetchall()
        expected = (
            ("PLANNED", "RUNNING") if job == active_job else ("PLANNED", "RUNNING", "SUCCEEDED")
        )
        if (
            parent is not None
            or command != COMMAND
            or not pin(config)
            or any(
                not isinstance(x, str) or not 0 < len(x) <= 4096 or x != x.strip()
                for x in (actor, revision)
            )
            or not isinstance(clock, datetime)
            or clock.tzinfo is None
            or tuple(row[0] for row in events) != tuple(range(1, len(expected) + 1))
            or tuple(row[1] for row in events) != expected
            or any(
                row[3] is not None or not isinstance(row[2], datetime) or row[2].tzinfo is None
                for row in events
            )
        ):
            raise CheckpointReviewRequired("CHECKPOINT_FAILED_OR_INCOMPLETE_AUDIT_OBLIGATION")
        if job != active_job and (job not in linked or linked[job] != config):
            raise CheckpointReviewRequired("CHECKPOINT_AUDIT_ATTEMPT_CONFIG_MISMATCH")
        audit_rows.append(
            [
                job,
                parent,
                command,
                config,
                clock.astimezone(UTC).isoformat(),
                actor,
                revision,
                [[r[0], r[1], r[2].astimezone(UTC).isoformat(), r[3]] for r in events],
            ]
        )
    job_ids = {row[0] for row in jobs}
    if active_job is not None and active_job not in job_ids:
        raise CheckpointReviewRequired("CHECKPOINT_ACTIVE_JOB_NOT_SCOPED")
    if any(job not in job_ids for job in linked) or any(
        origin not in linked or linked[origin] != key for key, origin in origins.items()
    ):
        raise CheckpointReviewRequired("CHECKPOINT_ORIGIN_NOT_LINKED")
    fingerprint = sha(
        canonical(
            [
                VERSION,
                scope,
                [
                    [item.checkpoint_id, asdict(item), origins[item.checkpoint_id]]
                    for item in ordered
                ],
                attempts,
                audit_rows,
                [[row[0], row[4].astimezone(UTC).isoformat()] for row in sorted(records)],
            ]
        ).encode()
    )
    return CheckpointView(scope, head, tuple(item.checkpoint_id for item in ordered), fingerprint)


def read_policy_checkpoint(
    conn: Any, *, policy_id: str, governance_key_sha256: str
) -> CheckpointView:
    scope = series_id(policy_id, governance_key_sha256)
    conn.execute("BEGIN TRANSACTION")
    try:
        result = _snapshot(conn, scope)
        conn.execute("COMMIT")
        return result
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def record_policy_checkpoint(
    conn: Any,
    *,
    snapshots: tuple[SignedPolicyInput, ...],
    governance_public_key: bytes,
    expected_governance_key_sha256: str,
    query: ScopeQuery,
    anchor: PolicyPosition,
    tip: PolicyPosition,
    expected_previous_id: str | None,
    actor_id: str,
    code_revision: str,
    initialize: bool = False,
) -> dict[str, object]:
    from nse_quant.data_platform import signed_policy_window as signed
    from nse_quant.data_platform.audit import AuditLedger

    if type(initialize) is not bool or any(
        not isinstance(value, str)
        or not 0 < len(value) <= 256
        or value != value.strip()
        or any(ord(c) < 32 for c in value)
        for value in (actor_id, code_revision)
    ):
        raise ValueError("BOUNDED_CHECKPOINT_EXECUTION_IDENTIFIERS_REQUIRED")
    if signed.VERSION != "signed-scope-policy-window@1":
        raise ValueError("UNSUPPORTED_CHECKPOINT_WINDOW_VERSION")
    if expected_previous_id is not None and not pin(expected_previous_id):
        raise ValueError("EXACT_EXPECTED_CHECKPOINT_ID_REQUIRED")
    result = signed.inspect_signed_policy_window(
        snapshots,
        governance_public_key=governance_public_key,
        expected_governance_key_sha256=expected_governance_key_sha256,
        query=query,
        anchor=anchor,
        tip=tip,
    )
    # Recording a denying snapshot must remain possible: no query-grant filter.
    if not result.window.window_constraints_satisfied or not pin(result.evidence_fingerprint):
        raise ValueError("CHECKPOINT_SIGNED_WINDOW_CONSTRAINTS_NOT_SATISFIED")
    last = result.observations[-1]
    scope = series_id(last.policy_id, expected_governance_key_sha256)
    denied = tuple(sorted(json.loads(snapshots[-1].policy_bytes)["denied_keys"]))
    candidate = CheckpointRecord(
        scope,
        expected_previous_id,
        anchor.sequence,
        anchor.policy_sha256,
        tip.sequence,
        tip.policy_sha256,
        denied,
        result.evidence_fingerprint,
    )
    if initialize:
        initialize_policy_checkpoints(conn)
    _owned(conn)
    # Resolve every prior obligation before planning a new job; no later-success repair.
    read_policy_checkpoint(
        conn, policy_id=last.policy_id, governance_key_sha256=expected_governance_key_sha256
    )
    ledger = AuditLedger(conn)
    job = ledger.plan_job(
        command_name=COMMAND,
        actor_id=actor_id,
        scope_ref=scope,
        code_revision=code_revision,
        config_hash=candidate.checkpoint_id,
    )
    with ledger.execution(job):
        conn.execute("BEGIN TRANSACTION")
        try:
            view = _snapshot(conn, scope, active_job=job)
            retry = candidate.checkpoint_id in view.checkpoint_ids
            if not retry:
                if (view.head.checkpoint_id if view.head else None) != expected_previous_id:
                    raise ValueError("CHECKPOINT_EXPECTED_HEAD_MISMATCH")
                validate_extension(view.head, candidate)
                if len(view.checkpoint_ids) >= MAX_RECORDS:
                    raise ValueError("CHECKPOINT_HISTORY_CAPACITY")
                records_table = _name(conn, "policy_checkpoint", "records")
                conn.execute(
                    f"INSERT INTO {records_table} VALUES (?,?,?,?,?)",
                    [
                        candidate.checkpoint_id,
                        scope,
                        canonical(asdict(candidate)),
                        job,
                        datetime.now(UTC),
                    ],
                )
            attempts_table = _name(conn, "policy_checkpoint", "attempts")
            conn.execute(
                f"INSERT INTO {attempts_table} VALUES (?,?,?)",
                [job, scope, candidate.checkpoint_id],
            )
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
    return {
        "status": "recorded_local_policy_checkpoint",
        "checkpoint_id": candidate.checkpoint_id,
        "job_id": job,
        "exact_retry": retry,
        "policy_currentness_verified": False,
        "policy_authority_authenticated": False,
        "decision_eligibility_asserted": False,
    }
