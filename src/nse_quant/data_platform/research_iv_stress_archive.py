"""Dedicated audited first-write native stress archive, not publication/current eligibility."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nse_quant.data_platform import research_iv_stress_archive_record as record

VERSION = "audited-research-iv-spot-stress-recording@1"
COMMAND = "record.research_iv_spot_stress@1"
TABLE = "research_iv_spot_stress_records"


class IvStressArchiveReviewRequired(ValueError):
    """Original audit/domain obligation incomplete. No retry or later-success repair."""


@dataclass(frozen=True)
class ResearchIvStressRecording:
    version: str
    build_id: str
    recorded_native_status: str
    record_json: str
    evidence_fingerprint: str
    status: str = "recorded_research_iv_spot_stress_not_published"
    original_recording_checked: bool = True
    current_source_checked: bool = False
    model_computation_rechecked: bool = False
    portfolio_pnl_asserted: bool = False
    publication_asserted: bool = False
    decision_eligibility_asserted: bool = False
    canonical_contract_id: None = None
    event_ts: None = None
    published_at: None = None


def _name(conn: Any, schema: str, table: str) -> str:
    row = conn.execute("SELECT current_database()").fetchone()
    if row is None:
        raise ValueError("STRESS_ARCHIVE_CATALOG_REQUIRED")
    return ".".join('"' + str(v).replace('"', '""') + '"' for v in (row[0], schema, table))


def _paths(conn: Any) -> tuple[Path, ...]:
    return tuple(Path(r[2]) for r in conn.execute("PRAGMA database_list").fetchall() if r[2])


def _owned(conn: Any) -> None:
    row = conn.execute("SELECT current_database()").fetchone()
    if row is None or not any(
        r[1] == row[0] and r[2] for r in conn.execute("PRAGMA database_list").fetchall()
    ):
        raise ValueError("STRESS_ARCHIVE_FILE_BACKED_TARGET_REQUIRED")
    allowed = {("gold", TABLE)} | {
        ("medallion_audit", n)
        for n in (
            "schema_versions",
            "dataset_contracts",
            "jobs",
            "job_events",
        )
    }
    rows = conn.execute(
        "SELECT table_schema,table_name FROM information_schema.tables "
        "WHERE table_catalog=current_database()"
    ).fetchall()
    if any(tuple(r) not in allowed for r in rows):
        raise ValueError("STRESS_ARCHIVE_DEDICATED_TARGET_REQUIRED")


def _contract() -> Any:
    from nse_quant.data_platform.contracts import DatasetContract, Layer, WritePolicy

    return DatasetContract(
        "gold." + TABLE,
        "1",
        Layer.GOLD,
        WritePolicy.VERSIONED_BUILDS,
        ("build_id",),
        ("build_id", "event_ts", "published_at", "feature_version"),
        "native_research_iv_spot_stress_archive",
    )


def _instant(value: object) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise IvStressArchiveReviewRequired("STRESS_ARCHIVE_AWARE_CLOCK_REQUIRED")
    return value.astimezone(UTC).isoformat()


def _identifier(value: object) -> bool:
    return (
        type(value) is str
        and 0 < len(value) <= 256
        and value == value.strip()
        and all(ord(c) >= 32 for c in value)
    )


def _snapshot(conn: Any, active_job: str | None = None, active_scope: str | None = None) -> str:
    """Whole store, all scopes/jobs/events. No filtering away original failures."""
    _owned(conn)
    schema = conn.execute(
        "SELECT version,applied_at FROM "
        f"{_name(conn, 'medallion_audit', 'schema_versions')} LIMIT 2"
    ).fetchall()
    if len(schema) != 1 or schema[0][0] != 1:
        raise IvStressArchiveReviewRequired("STRESS_ARCHIVE_SCHEMA_MISMATCH")
    rows = conn.execute(
        "SELECT build_id,scope_id,CASE WHEN octet_length(encode(record_json))<=? "
        "THEN record_json END,feature_version,first_job_id,recorded_at,event_ts,published_at "
        f"FROM {_name(conn, 'gold', TABLE)} LIMIT 2",
        [record.MAX_RECORD_BYTES],
    ).fetchall()
    contracts = conn.execute(
        "SELECT dataset_name,contract_version,fingerprint,"
        "CASE WHEN octet_length(encode(contract_json))<=32768 THEN contract_json END,registered_at "
        f"FROM {_name(conn, 'medallion_audit', 'dataset_contracts')} LIMIT 2"
    ).fetchall()
    jobs = conn.execute(
        "SELECT job_id,parent_job_id,command_name,actor_id,scope_ref,"
        "code_revision,config_hash,created_at "
        f"FROM {_name(conn, 'medallion_audit', 'jobs')} ORDER BY job_id LIMIT 17"
    ).fetchall()
    events = conn.execute(
        "SELECT job_id,event_index,state,recorded_at,reason_code FROM "
        f"{_name(conn, 'medallion_audit', 'job_events')} ORDER BY job_id,event_index LIMIT 65"
    ).fetchall()
    if len(rows) > 1 or len(contracts) > 1 or len(jobs) > 16 or len(events) > 64:
        raise IvStressArchiveReviewRequired("STRESS_ARCHIVE_PROFILE_LIMIT")
    origin: str | None = None
    scope: str | None = None
    normalized_rows: list[object] = []
    if rows:
        row = rows[0]
        body = record.decode(row[2])
        scope = record.scope(body["request"])
        origin = row[4]
        if (
            row[0] != record.sha(row[2].encode())
            or row[1] != scope
            or row[3] != VERSION
            or not _identifier(origin)
            or row[6:] != (None, None)
        ):
            raise IvStressArchiveReviewRequired("STRESS_ARCHIVE_ROW_MISMATCH")
        contract = _contract()
        if len(contracts) != 1 or contracts[0][:4] != (
            contract.name,
            contract.version,
            contract.fingerprint,
            contract.canonical_json(),
        ):
            raise IvStressArchiveReviewRequired("STRESS_ARCHIVE_CONTRACT_MISMATCH")
        normalized_rows.append([*row[:5], _instant(row[5]), None, None])
    elif contracts:
        raise IvStressArchiveReviewRequired("STRESS_ARCHIVE_ORPHAN_CONTRACT")
    job_ids = {j[0] for j in jobs}
    if any(e[0] not in job_ids for e in events):
        raise IvStressArchiveReviewRequired("STRESS_ARCHIVE_ORPHAN_EVENTS")
    if (
        origin is not None
        and origin not in job_ids
        or active_job is not None
        and active_job not in job_ids
    ):
        raise IvStressArchiveReviewRequired("STRESS_ARCHIVE_ORIGIN_MISSING")
    normalized_jobs: list[object] = []
    normalized_events: list[object] = []
    config_hash = record.sha(record.canonical(record.DEFINITION).encode())
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
            or config != config_hash
            or group != (active_scope if active else scope)
            or not active
            and job != origin
            or any(type(e[1]) is not int or e[4] is not None for e in selected)
            or tuple(e[1] for e in selected) != tuple(range(1, len(expected) + 1))
            or tuple(e[2] for e in selected) != expected
        ):
            raise IvStressArchiveReviewRequired("STRESS_ARCHIVE_FAILED_INCOMPLETE_UNLINKED_JOB")
        normalized_jobs.append(
            [job, parent, command, actor, group, revision, config, _instant(created)]
        )
        normalized_events.extend([*e[:3], _instant(e[3]), e[4]] for e in selected)
    return record.sha(
        record.canonical(
            [
                VERSION,
                _instant(schema[0][1]),
                normalized_rows,
                [[*c[:4], _instant(c[4])] for c in contracts],
                normalized_jobs,
                normalized_events,
            ]
        ).encode()
    )


def _initialize(conn: Any) -> None:
    from nse_quant.data_platform.audit import AuditLedger

    _owned(conn)
    if (
        conn.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_catalog=current_database() LIMIT 1"
        ).fetchone()
        is not None
    ):
        raise ValueError("STRESS_ARCHIVE_NEW_EMPTY_TARGET_REQUIRED")
    AuditLedger(conn).initialize()
    conn.execute("BEGIN TRANSACTION")
    try:
        conn.execute(f"CREATE SCHEMA {_name(conn, 'gold', TABLE).rsplit('.', 1)[0]}")
        conn.execute(
            f"CREATE TABLE {_name(conn, 'gold', TABLE)} ("
            "build_id VARCHAR PRIMARY KEY,scope_id VARCHAR UNIQUE NOT NULL,"
            "record_json VARCHAR NOT NULL,feature_version VARCHAR NOT NULL,"
            "first_job_id VARCHAR NOT NULL,recorded_at TIMESTAMPTZ NOT NULL,"
            "event_ts TIMESTAMPTZ,published_at TIMESTAMPTZ)"
        )
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def persist_research_iv_spot_stress(
    bronze: Any,
    frame_silver: Any,
    reference_silver: Any,
    assessments: Any,
    source_gold: Any,
    archive: Any,
    target: Any,
    *,
    build_id_pin: str,
    expected_archive_fingerprint: str,
    expected_revalidation_fingerprint: str,
    shocks_bps: tuple[int, ...],
    actor_id: str,
    code_revision: str,
    initialize: bool = False,
) -> ResearchIvStressRecording:
    """One actual native invocation (already internally revalidates/repeats); retain negatives."""
    from nse_quant.data_platform import native_research_iv_spot_stress as native
    from nse_quant.data_platform import research_iv_spot_stress as stress
    from nse_quant.data_platform.audit import AuditLedger

    if (
        native.VERSION != record.NATIVE_VERSION
        or native.MAX_NATIVE_BYTES != record.MAX_NATIVE_BYTES
        or stress.VERSION != "research-iv-fixed-vol-spot-stress@1"
        or stress.MAX_SHOCKS != 16
        or stress.MAX_RESULT_BYTES != record.MAX_STUDY_BYTES
    ):
        raise ValueError("STRESS_ARCHIVE_UNSUPPORTED_NATIVE_PROFILE")
    requested = record.request(
        (build_id_pin, expected_archive_fingerprint, expected_revalidation_fingerprint), shocks_bps
    )
    if not _identifier(actor_id) or not _identifier(code_revision) or type(initialize) is not bool:
        raise ValueError("STRESS_ARCHIVE_EXECUTION_IDENTIFIERS_REQUIRED")
    _owned(target)
    inputs = (bronze, frame_silver, reference_silver, assessments, source_gold, archive)
    for conn in inputs:
        if conn is target or any(
            a == b or a.samefile(b) for a in _paths(target) for b in _paths(conn)
        ):
            raise ValueError("STRESS_ARCHIVE_SEPARATE_OUTPUT_REQUIRED")
    if initialize:
        _initialize(target)
    _snapshot(target)
    existing = target.execute(f"SELECT 1 FROM {_name(target, 'gold', TABLE)} LIMIT 1").fetchone()
    if existing is not None:
        raise IvStressArchiveReviewRequired("STRESS_ARCHIVE_EXISTS_NO_RETRY")
    scope = record.scope(requested)
    ledger = AuditLedger(target)
    job = ledger.plan_job(
        command_name=COMMAND,
        actor_id=actor_id,
        scope_ref=scope,
        code_revision=code_revision,
        config_hash=record.sha(record.canonical(record.DEFINITION).encode()),
    )
    with ledger.execution(job):
        observed = native.build_native_research_iv_spot_stress(
            *inputs,
            build_id_pin=build_id_pin,
            expected_archive_fingerprint=expected_archive_fingerprint,
            expected_revalidation_fingerprint=expected_revalidation_fingerprint,
            shocks_bps=shocks_bps,
        )
        if type(observed) is not native.NativeResearchIvSpotStress:
            raise ValueError("STRESS_ARCHIVE_TYPED_NATIVE_RESULT_REQUIRED")
        raw = record.encode(requested, asdict(observed))
        key = record.sha(raw.encode())
        target.execute("BEGIN TRANSACTION")
        try:
            _snapshot(target, job, scope)
            if target.execute(f"SELECT 1 FROM {_name(target, 'gold', TABLE)} LIMIT 1").fetchone():
                raise IvStressArchiveReviewRequired("STRESS_ARCHIVE_CONCURRENT_RECORD")
            ledger.register_contract(_contract())
            target.execute(
                f"INSERT INTO {_name(target, 'gold', TABLE)} VALUES (?,?,?,?,?,?,?,?)",
                [key, scope, raw, VERSION, job, datetime.now(UTC), None, None],
            )
            target.execute("COMMIT")
        except BaseException:
            target.execute("ROLLBACK")
            raise
    return read_research_iv_spot_stress_archive(target, build_id_pin=key)


def read_research_iv_spot_stress_archive(
    target: Any, *, build_id_pin: str
) -> ResearchIvStressRecording:
    """Original recording only: no source/current pricing, numerical computation or repair."""
    if not record.pin(build_id_pin):
        raise ValueError("STRESS_ARCHIVE_EXACT_RECORD_PIN_REQUIRED")
    target.execute("BEGIN TRANSACTION")
    try:
        fingerprint = _snapshot(target)
        rows = target.execute(
            "SELECT CASE WHEN octet_length(encode(record_json))<=? THEN record_json END "
            f"FROM {_name(target, 'gold', TABLE)} WHERE build_id=? LIMIT 2",
            [record.MAX_RECORD_BYTES, build_id_pin],
        ).fetchall()
        if len(rows) != 1:
            raise IvStressArchiveReviewRequired("STRESS_ARCHIVE_EXACT_RECORD_NOT_FOUND")
        raw = rows[0][0]
        body = record.decode(raw)
        if record.sha(raw.encode()) != build_id_pin or fingerprint != _snapshot(target):
            raise IvStressArchiveReviewRequired("STRESS_ARCHIVE_RECORDING_CHANGED")
        target.execute("COMMIT")
    except BaseException:
        target.execute("ROLLBACK")
        raise
    return ResearchIvStressRecording(
        VERSION,
        build_id_pin,
        body["result"]["status"],
        raw,
        fingerprint,
    )
