"""Audited immutable capture of actual recovery plans; no recovery execution API."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nse_quant.data_platform.research_iv_recovery_capture_record import (
    MAX_RECORD_BYTES,
    SERVICE_VERSION,
    canonical,
    decode,
    encode,
    pin,
    sha,
)

VERSION = "audited-research-iv-recovery-capture@1"
COMMAND = "capture.research_iv_recovery@1"
TABLE = "research_iv_recovery_captures"
DEFINITION = (
    VERSION,
    SERVICE_VERSION,
    "research-iv-recovery-capture-record@1",
    "single-capture-no-retry-no-recovery@1",
)


class IvRecoveryCaptureReviewRequired(ValueError):
    """Original recording obligations failed; no retry or later-good repair."""


@dataclass(frozen=True)
class ResearchIvRecoveryCapture:
    version: str
    build_id: str
    record_json: str
    evidence_fingerprint: str
    status: str = "recorded_recovery_observation_not_execution_authorization"
    original_recording_checked: bool = True
    current_reconciliation_checked: bool = False
    recovery_execution_authorized: bool = False
    publication_asserted: bool = False
    decision_eligibility_asserted: bool = False
    event_ts: None = None
    published_at: None = None


def _name(conn: Any, schema: str, table: str) -> str:
    row = conn.execute("SELECT current_database()").fetchone()
    if row is None:
        raise ValueError("IV_RECOVERY_CAPTURE_CATALOG_REQUIRED")
    return ".".join('"' + str(v).replace('"', '""') + '"' for v in (row[0], schema, table))


def _paths(conn: Any) -> tuple[Path, ...]:
    return tuple(Path(row[2]) for row in conn.execute("PRAGMA database_list").fetchall() if row[2])


def _owned(conn: Any) -> None:
    row = conn.execute("SELECT current_database()").fetchone()
    if row is None or not any(
        r[1] == row[0] and r[2] for r in conn.execute("PRAGMA database_list").fetchall()
    ):
        raise ValueError("IV_RECOVERY_CAPTURE_FILE_BACKED_TARGET_REQUIRED")
    allowed = {("gold", TABLE)} | {
        ("medallion_audit", n)
        for n in ("schema_versions", "dataset_contracts", "jobs", "job_events")
    }
    tables = conn.execute(
        "SELECT table_schema,table_name FROM information_schema.tables "
        "WHERE table_catalog=current_database()"
    ).fetchall()
    if any(tuple(r) not in allowed for r in tables):
        raise ValueError("IV_RECOVERY_CAPTURE_DEDICATED_TARGET_REQUIRED")


def _contract() -> Any:
    from nse_quant.data_platform.contracts import DatasetContract, Layer, WritePolicy

    return DatasetContract(
        "gold." + TABLE,
        "1",
        Layer.GOLD,
        WritePolicy.VERSIONED_BUILDS,
        ("build_id",),
        ("build_id", "event_ts", "published_at", "feature_version"),
        "native_research_iv_recovery_capture",
    )


def _instant(value: object) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise IvRecoveryCaptureReviewRequired("IV_RECOVERY_CAPTURE_AWARE_CLOCK_REQUIRED")
    return value.astimezone(UTC).isoformat()


def _identifier(value: object) -> bool:
    return (
        type(value) is str
        and 0 < len(value) <= 256
        and value == value.strip()
        and all(ord(c) >= 32 for c in value)
    )


def _snapshot(conn: Any, active_job: str | None = None, scope: str | None = None) -> str:
    """Check WHOLE dedicated store, including failed, incomplete and orphan events."""
    _owned(conn)
    versions = conn.execute(
        f"SELECT version,applied_at FROM {_name(conn, 'medallion_audit', 'schema_versions')} "
        "LIMIT 2"
    ).fetchall()
    if len(versions) != 1 or versions[0][0] != 1:
        raise IvRecoveryCaptureReviewRequired("IV_RECOVERY_CAPTURE_SCHEMA_REQUIRED")
    applied = _instant(versions[0][1])
    rows = conn.execute(
        "SELECT build_id,scope_id,CASE WHEN octet_length(encode(record_json))<=? "
        "THEN record_json END,feature_version,first_job_id,recorded_at,event_ts,published_at "
        f"FROM {_name(conn, 'gold', TABLE)} ORDER BY build_id LIMIT 2",
        [MAX_RECORD_BYTES],
    ).fetchall()
    contracts = conn.execute(
        "SELECT dataset_name,contract_version,fingerprint,"
        "CASE WHEN octet_length(encode(contract_json))<=32768 THEN contract_json END,registered_at "
        f"FROM {_name(conn, 'medallion_audit', 'dataset_contracts')} LIMIT 2"
    ).fetchall()
    jobs = conn.execute(
        "SELECT job_id,parent_job_id,command_name,actor_id,scope_ref,code_revision,"
        f"config_hash,created_at FROM {_name(conn, 'medallion_audit', 'jobs')} "
        "ORDER BY job_id LIMIT 17"
    ).fetchall()
    events = conn.execute(
        "SELECT job_id,event_index,state,recorded_at,reason_code FROM "
        f"{_name(conn, 'medallion_audit', 'job_events')} ORDER BY job_id,event_index LIMIT 65"
    ).fetchall()
    if len(rows) > 1 or len(contracts) > 1 or len(jobs) > 16 or len(events) > 64:
        raise IvRecoveryCaptureReviewRequired("IV_RECOVERY_CAPTURE_PROFILE_LIMIT")
    origin = None
    record_scope = None
    normalized_rows: list[object] = []
    if rows:
        r = rows[0]
        body = decode(r[2])
        record_scope = _scope(
            body["plan"]["stage_build_id"],
            body["plan"]["expected_stage_fingerprint"],
            body["plan"]["evidence_fingerprint"],
            body["artifact_root"],
        )
        origin = r[4]
        if (
            r[0] != sha(r[2].encode())
            or r[1] != record_scope
            or r[3] != VERSION
            or r[6:] != (None, None)
        ):
            raise IvRecoveryCaptureReviewRequired("IV_RECOVERY_CAPTURE_ROW_MISMATCH")
        normalized_rows.append([*r[:5], _instant(r[5]), None, None])
        contract = _contract()
        if len(contracts) != 1 or contracts[0][:4] != (
            contract.name,
            contract.version,
            contract.fingerprint,
            contract.canonical_json(),
        ):
            raise IvRecoveryCaptureReviewRequired("IV_RECOVERY_CAPTURE_CONTRACT_MISMATCH")
    elif contracts:
        raise IvRecoveryCaptureReviewRequired("IV_RECOVERY_CAPTURE_ORPHAN_CONTRACT")
    normalized_jobs: list[object] = []
    normalized_events: list[object] = []
    job_ids = {r[0] for r in jobs}
    if any(e[0] not in job_ids for e in events):
        raise IvRecoveryCaptureReviewRequired("IV_RECOVERY_CAPTURE_ORPHAN_EVENTS")
    for job, parent, command, actor, group, revision, config, created in jobs:
        active = job == active_job
        expected = ("PLANNED", "RUNNING") if active else ("PLANNED", "RUNNING", "SUCCEEDED")
        selected = [e for e in events if e[0] == job]
        if (
            not _identifier(job)
            or parent is not None
            or command != COMMAND
            or not _identifier(actor)
            or not _identifier(revision)
            or group != (scope if active else record_scope)
            or config != sha(canonical(DEFINITION).encode())
            or tuple(e[1] for e in selected) != tuple(range(1, len(expected) + 1))
            or any(type(e[1]) is not int or e[4] is not None for e in selected)
            or tuple(e[2] for e in selected) != expected
            or not active
            and job != origin
        ):
            raise IvRecoveryCaptureReviewRequired("IV_RECOVERY_CAPTURE_ORIGINAL_OBLIGATION_FAILED")
        normalized_jobs.append(
            [job, parent, command, actor, group, revision, config, _instant(created)]
        )
        normalized_events.extend([*e[:3], _instant(e[3]), e[4]] for e in selected)
    if (
        origin is not None
        and origin not in job_ids
        or active_job is not None
        and active_job not in job_ids
    ):
        raise IvRecoveryCaptureReviewRequired("IV_RECOVERY_CAPTURE_ORIGIN_MISSING")
    normalized_contracts = [[*c[:4], _instant(c[4])] for c in contracts]
    return sha(
        canonical(
            [
                VERSION,
                applied,
                normalized_rows,
                normalized_contracts,
                normalized_jobs,
                normalized_events,
            ]
        ).encode()
    )


def _scope(stage: str, fingerprint: str, plan: str, root: str) -> str:
    return sha(canonical([VERSION, stage, fingerprint, plan, root]).encode())


def _initialize(conn: Any) -> None:
    from nse_quant.data_platform.audit import AuditLedger

    _owned(conn)
    if (
        conn.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_catalog=current_database() LIMIT 1"
        ).fetchone()
        is not None
    ):
        raise ValueError("IV_RECOVERY_CAPTURE_NEW_EMPTY_TARGET_REQUIRED")
    AuditLedger(conn).initialize()
    conn.execute("BEGIN TRANSACTION")
    try:
        schema = _name(conn, "gold", TABLE).rsplit(".", 1)[0]
        conn.execute(f"CREATE SCHEMA {schema}")
        conn.execute(
            f"CREATE TABLE {_name(conn, 'gold', TABLE)} (build_id VARCHAR PRIMARY KEY,"
            "scope_id VARCHAR UNIQUE NOT NULL,record_json VARCHAR NOT NULL,"
            "feature_version VARCHAR NOT NULL,first_job_id VARCHAR NOT NULL,"
            "recorded_at TIMESTAMPTZ NOT NULL,event_ts TIMESTAMPTZ,published_at TIMESTAMPTZ)"
        )
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def capture_research_iv_recovery(
    staging: Any,
    target: Any,
    *,
    stage_build_id_pin: str,
    expected_stage_fingerprint: str,
    expected_plan_fingerprint: str,
    artifact_root: Path,
    actor_id: str,
    code_revision: str,
    initialize: bool = False,
) -> ResearchIvRecoveryCapture:
    """Actual two plans, frozen complete bytes. One capture; no retries or caller DTOs."""
    from nse_quant.data_platform import research_iv_recovery_plan as native
    from nse_quant.data_platform.audit import AuditLedger

    if native.VERSION != SERVICE_VERSION or native.MAX_PLAN_BYTES != 262144:
        raise ValueError("IV_RECOVERY_CAPTURE_UNSUPPORTED_NATIVE_PROFILE")
    if not all(
        pin(p) for p in (stage_build_id_pin, expected_stage_fingerprint, expected_plan_fingerprint)
    ) or (
        not _identifier(actor_id) or not _identifier(code_revision) or type(initialize) is not bool
    ):
        raise ValueError("IV_RECOVERY_CAPTURE_EXACT_PINS_AND_IDENTIFIERS_REQUIRED")
    if not artifact_root.is_absolute() or ".." in artifact_root.parts:
        raise ValueError("IV_RECOVERY_CAPTURE_ABSOLUTE_ROOT_REQUIRED")
    _owned(target)
    if staging is target or any(
        a == b or a.samefile(b) for a in _paths(staging) for b in _paths(target)
    ):
        raise ValueError("IV_RECOVERY_CAPTURE_SEPARATE_DATABASE_REQUIRED")
    for path in (artifact_root, *artifact_root.parents):
        if path.is_symlink() or path.is_junction():
            raise ValueError("IV_RECOVERY_CAPTURE_REDIRECTED_ROOT")
    resolved = artifact_root.resolve()
    databases = (*_paths(staging), *_paths(target))
    for path in databases:
        selected = path.resolve()
        if resolved == selected or resolved in selected.parents or selected in resolved.parents:
            raise ValueError("IV_RECOVERY_CAPTURE_DATABASE_ROOT_OVERLAP")
    if any(child.samefile(path) for child in artifact_root.iterdir() for path in databases):
        raise ValueError("IV_RECOVERY_CAPTURE_DATABASE_ARTIFACT_HARDLINK")
    if initialize:
        _initialize(target)
    _snapshot(target)
    if target.execute(f"SELECT 1 FROM {_name(target, 'gold', TABLE)} LIMIT 1").fetchone():
        raise IvRecoveryCaptureReviewRequired("IV_RECOVERY_CAPTURE_EXISTS_NO_RETRY")
    group = _scope(
        stage_build_id_pin,
        expected_stage_fingerprint,
        expected_plan_fingerprint,
        str(artifact_root),
    )
    ledger = AuditLedger(target)
    job = ledger.plan_job(
        command_name=COMMAND,
        actor_id=actor_id,
        scope_ref=group,
        code_revision=code_revision,
        config_hash=sha(canonical(DEFINITION).encode()),
    )
    with ledger.execution(job):

        def observe() -> str:
            value = native.plan_research_iv_stage_recovery(
                staging,
                stage_build_id_pin=stage_build_id_pin,
                expected_stage_fingerprint=expected_stage_fingerprint,
                artifact_root=artifact_root,
            )
            if type(value) is not native.ResearchIvRecoveryPlan:
                raise ValueError("IV_RECOVERY_CAPTURE_TYPED_NATIVE_PLAN_REQUIRED")
            if (
                value.stage_build_id != stage_build_id_pin
                or value.expected_stage_fingerprint != expected_stage_fingerprint
                or value.evidence_fingerprint != expected_plan_fingerprint
            ):
                raise ValueError("IV_RECOVERY_CAPTURE_REVIEWED_PLAN_CHANGED")
            return encode(str(artifact_root), asdict(value))

        first = observe()
        second = observe()
        if first != second:
            raise ValueError("IV_RECOVERY_CAPTURE_NATIVE_PLAN_BYTES_CHANGED")
        key = sha(first.encode())
        target.execute("BEGIN TRANSACTION")
        try:
            _snapshot(target, job, group)
            if target.execute(f"SELECT 1 FROM {_name(target, 'gold', TABLE)} LIMIT 1").fetchone():
                raise IvRecoveryCaptureReviewRequired("IV_RECOVERY_CAPTURE_CONCURRENT_RECORD")
            ledger.register_contract(_contract())
            target.execute(
                f"INSERT INTO {_name(target, 'gold', TABLE)} VALUES (?,?,?,?,?,?,?,?)",
                [key, group, first, VERSION, job, datetime.now(UTC), None, None],
            )
            target.execute("COMMIT")
        except BaseException:
            target.execute("ROLLBACK")
            raise
    return read_research_iv_recovery_capture(target, build_id_pin=key)


def read_research_iv_recovery_capture(
    target: Any, *, build_id_pin: str
) -> ResearchIvRecoveryCapture:
    """Original recording verification only. No stage, filesystem or current source reads."""
    if not pin(build_id_pin):
        raise ValueError("IV_RECOVERY_CAPTURE_EXACT_BUILD_PIN_REQUIRED")
    target.execute("BEGIN TRANSACTION")
    try:
        first = _snapshot(target)
        row = target.execute(
            "SELECT CASE WHEN octet_length(encode(record_json))<=? THEN record_json END "
            f"FROM {_name(target, 'gold', TABLE)} WHERE build_id=? LIMIT 2",
            [MAX_RECORD_BYTES, build_id_pin],
        ).fetchall()
        if len(row) != 1:
            raise IvRecoveryCaptureReviewRequired("IV_RECOVERY_CAPTURE_EXACT_RECORD_REQUIRED")
        raw = row[0][0]
        decode(raw)
        if sha(raw.encode()) != build_id_pin or first != _snapshot(target):
            raise IvRecoveryCaptureReviewRequired("IV_RECOVERY_CAPTURE_RECORD_CHANGED")
        target.execute("COMMIT")
    except BaseException:
        target.execute("ROLLBACK")
        raise
    return ResearchIvRecoveryCapture(VERSION, build_id_pin, raw, first)
