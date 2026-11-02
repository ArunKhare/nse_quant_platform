"""Audited first-write research-IV stage binding; no retry/adoption/publication."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nse_quant.data_platform.research_iv_stage_record import (
    DEFINITION,
    FLAGS,
    MAX_RECORD_BYTES,
    build_id,
    canonical,
    decode,
    pin,
    scope,
    sha,
)

VERSION = "audited-research-iv-first-stage@1"
COMMAND = "stage.research_iv_first_binding@1"
FEATURE = "research-iv-first-stage@1"
TABLES = (
    "research_iv_first_stage_schema",
    "research_iv_first_stages",
    "research_iv_first_attempts",
)
MAX_JOBS = 16


class IvFirstStageReviewRequired(ValueError):
    """An original obligation is incomplete. No retry or later success may repair it."""


class IvFirstStageNativeRejected(ValueError):
    def __init__(self, observation: Any) -> None:
        super().__init__("IV_FIRST_STAGE_NATIVE_MATERIALIZATION_REVIEW_REQUIRED")
        self.observation = observation


@dataclass(frozen=True)
class ResearchIvFirstStage:
    version: str
    build_id: str
    status: str
    record_json: str
    evidence_fingerprint: str
    archived_stage_recording_verified: bool = True
    artifact_bytes_checked: bool = True
    current_source_checked: bool = False
    publication_asserted: bool = False
    decision_eligibility_asserted: bool = False
    canonical_contract_id: None = None


def _name(conn: Any, schema: str, table: str) -> str:
    row = conn.execute("SELECT current_database()").fetchone()
    if row is None:
        raise ValueError("IV_FIRST_STAGE_CATALOG_REQUIRED")
    return ".".join('"' + str(value).replace('"', '""') + '"' for value in (row[0], schema, table))


def _paths(conn: Any) -> tuple[Path, ...]:
    return tuple(Path(row[2]) for row in conn.execute("PRAGMA database_list").fetchall() if row[2])


def _owned(conn: Any) -> None:
    row = conn.execute("SELECT current_database()").fetchone()
    if row is None or not any(
        item[1] == row[0] and item[2] for item in conn.execute("PRAGMA database_list").fetchall()
    ):
        raise ValueError("FILE_BACKED_IV_FIRST_STAGE_REQUIRED")
    allowed = {("gold", name) for name in TABLES} | {
        ("medallion_audit", name)
        for name in ("schema_versions", "dataset_contracts", "jobs", "job_events")
    }
    rows = conn.execute(
        "SELECT table_schema,table_name FROM information_schema.tables "
        "WHERE table_catalog=current_database()"
    ).fetchall()
    if any(tuple(item) not in allowed for item in rows):
        raise ValueError("DEDICATED_IV_FIRST_STAGE_REQUIRED")


def _contract() -> Any:
    from nse_quant.data_platform.contracts import DatasetContract, Layer, WritePolicy

    return DatasetContract(
        "gold.research_iv_first_stages",
        "1",
        Layer.GOLD,
        WritePolicy.VERSIONED_BUILDS,
        ("build_id",),
        ("build_id", "event_ts", "published_at", "feature_version"),
        "native_research_iv_first_stage",
    )


def _instant(value: object) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise IvFirstStageReviewRequired("IV_FIRST_STAGE_AWARE_CLOCK_REQUIRED")
    return value.astimezone(UTC).isoformat()


def _identifier(value: object) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value) <= 256
        and value == value.strip()
        and all(ord(char) >= 32 for char in value)
    )


def _initialize(conn: Any) -> None:
    from nse_quant.data_platform.audit import AuditLedger

    _owned(conn)
    # This profile initializes ONLY a genuinely new empty target, never adopts one.
    if (
        conn.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_catalog=current_database() LIMIT 1"
        ).fetchone()
        is not None
    ):
        raise ValueError("NEW_EMPTY_IV_FIRST_STAGE_TARGET_REQUIRED")
    AuditLedger(conn).initialize()
    conn.execute("BEGIN TRANSACTION")
    try:
        schema = _name(conn, "gold", TABLES[0]).rsplit(".", 1)[0]
        conn.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
        conn.execute(f"CREATE TABLE {_name(conn, 'gold', TABLES[0])} (version INTEGER PRIMARY KEY)")
        conn.execute(f"INSERT INTO {_name(conn, 'gold', TABLES[0])} VALUES (1)")
        conn.execute(
            f"CREATE TABLE {_name(conn, 'gold', TABLES[1])} (build_id VARCHAR PRIMARY KEY,"
            "scope_id VARCHAR UNIQUE NOT NULL,record_json VARCHAR NOT NULL,"
            "feature_version VARCHAR NOT NULL,first_job_id VARCHAR NOT NULL,"
            "recorded_at TIMESTAMPTZ NOT NULL,event_ts TIMESTAMPTZ,published_at TIMESTAMPTZ)"
        )
        conn.execute(
            f"CREATE TABLE {_name(conn, 'gold', TABLES[2])} (job_id VARCHAR PRIMARY KEY,"
            "scope_id VARCHAR NOT NULL,build_id VARCHAR NOT NULL)"
        )
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def _snapshot(
    conn: Any, *, active_job: str | None = None, active_scope: str | None = None
) -> tuple[list[tuple[Any, ...]], str]:
    """WHOLE store before filtering: one retained binding, all original audit obligations."""
    _owned(conn)
    for schema, table in (("gold", TABLES[0]), ("medallion_audit", "schema_versions")):
        versions = conn.execute(
            f"SELECT version FROM {_name(conn, schema, table)} LIMIT 2"
        ).fetchall()
        if versions != [(1,)]:
            raise IvFirstStageReviewRequired("IV_FIRST_STAGE_SCHEMA_MISMATCH")
    rows = conn.execute(
        "SELECT build_id,scope_id,CASE WHEN octet_length(encode(record_json))<=? "
        "THEN record_json END,feature_version,first_job_id,recorded_at,event_ts,published_at "
        f"FROM {_name(conn, 'gold', TABLES[1])} ORDER BY build_id LIMIT 2",
        [MAX_RECORD_BYTES],
    ).fetchall()
    attempts = conn.execute(
        f"SELECT job_id,scope_id,build_id FROM {_name(conn, 'gold', TABLES[2])} "
        "ORDER BY job_id LIMIT 2"
    ).fetchall()
    contracts = conn.execute(
        "SELECT dataset_name,contract_version,fingerprint,"
        "CASE WHEN octet_length(encode(contract_json))<=32768 THEN contract_json END,registered_at "
        f"FROM {_name(conn, 'medallion_audit', 'dataset_contracts')} LIMIT 2"
    ).fetchall()
    jobs = conn.execute(
        "SELECT job_id,parent_job_id,command_name,scope_ref,config_hash,created_at,"
        "actor_id,code_revision "
        f"FROM {_name(conn, 'medallion_audit', 'jobs')} ORDER BY job_id LIMIT ?",
        [MAX_JOBS + 1],
    ).fetchall()
    if len(rows) > 1 or len(attempts) > 1 or len(contracts) > 1 or len(jobs) > MAX_JOBS:
        raise IvFirstStageReviewRequired("IV_FIRST_STAGE_PROFILE_LIMIT")
    normalized: list[object] = []
    record_scope: str | None = None
    origin: str | None = None
    if rows:
        row = rows[0]
        parsed = decode(row[2])
        record_scope = scope(tuple(parsed["pins"]), parsed["artifact_root"])
        origin = row[4]
        if (
            row[0] != build_id(row[2])
            or row[1] != record_scope
            or row[3] != FEATURE
            or row[6:] != (None, None)
            or attempts != [(origin, record_scope, row[0])]
        ):
            raise IvFirstStageReviewRequired("IV_FIRST_STAGE_RECORD_OR_ATTEMPT_MISMATCH")
        normalized.append([*row[:5], _instant(row[5]), None, None])
        contract = _contract()
        if len(contracts) != 1 or contracts[0][:4] != (
            contract.name,
            contract.version,
            contract.fingerprint,
            contract.canonical_json(),
        ):
            raise IvFirstStageReviewRequired("IV_FIRST_STAGE_CONTRACT_MISMATCH")
    elif attempts or contracts:
        raise IvFirstStageReviewRequired("IV_FIRST_STAGE_ORPHAN_DOMAIN")
    normalized_contracts = [[*row[:4], _instant(row[4])] for row in contracts]
    audit: list[object] = []
    for job, parent, command, group, config, created, actor, revision in jobs:
        is_active = job == active_job
        expected_scope = active_scope if is_active else record_scope
        expected: tuple[str, ...] = (
            ("PLANNED", "RUNNING") if is_active else ("PLANNED", "RUNNING", "SUCCEEDED")
        )
        events = conn.execute(
            "SELECT event_index,state,recorded_at,reason_code FROM "
            f"{_name(conn, 'medallion_audit', 'job_events')} "
            "WHERE job_id=? ORDER BY event_index LIMIT 7",
            [job],
        ).fetchall()
        if (
            parent is not None
            or command != COMMAND
            or group != expected_scope
            or config != sha(canonical(DEFINITION).encode())
            or not _identifier(actor)
            or not _identifier(revision)
            or any(type(item[0]) is not int for item in events)
            or tuple(item[0] for item in events) != tuple(range(1, len(expected) + 1))
            or tuple(item[1] for item in events) != expected
            or any(item[3] is not None for item in events)
            or not is_active
            and job != origin
        ):
            raise IvFirstStageReviewRequired("IV_FIRST_STAGE_FAILED_INCOMPLETE_UNLINKED_OBLIGATION")
        audit.append(
            [
                job,
                parent,
                command,
                group,
                config,
                _instant(created),
                actor,
                revision,
                [[item[0], item[1], _instant(item[2]), item[3]] for item in events],
            ]
        )
    job_ids = {row[0] for row in jobs}
    if (
        origin is not None
        and origin not in job_ids
        or active_job is not None
        and active_job not in job_ids
    ):
        raise IvFirstStageReviewRequired("IV_FIRST_STAGE_ORIGIN_MISSING")
    # Detect events with missing jobs rather than silently omitting them through joins.
    orphans = conn.execute(
        f"SELECT 1 FROM {_name(conn, 'medallion_audit', 'job_events')} e "
        f"LEFT JOIN {_name(conn, 'medallion_audit', 'jobs')} j ON e.job_id=j.job_id "
        "WHERE j.job_id IS NULL LIMIT 1"
    ).fetchone()
    if orphans is not None:
        raise IvFirstStageReviewRequired("IV_FIRST_STAGE_ORPHAN_AUDIT_EVENTS")
    content = [VERSION, normalized, attempts, normalized_contracts, audit]
    return rows, sha(canonical(content).encode())


def _transaction_snapshot(conn: Any) -> tuple[list[tuple[Any, ...]], str]:
    conn.execute("BEGIN TRANSACTION")
    try:
        value = _snapshot(conn)
        conn.execute("COMMIT")
        return value
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def stage_new_research_iv_artifact(
    bronze: Any,
    frame_silver: Any,
    reference_silver: Any,
    assessments: Any,
    source_gold: Any,
    archive: Any,
    bundle_archive: Any,
    target: Any,
    *,
    build_id_pin: str,
    expected_archive_fingerprint: str,
    expected_bundle_id: str,
    expected_revalidation_fingerprint: str,
    artifact_root: Path,
    actor_id: str,
    code_revision: str,
    initialize: bool = False,
    initialize_artifacts: bool = False,
) -> dict[str, object]:
    from nse_quant.data_platform import native_research_iv_artifact as native
    from nse_quant.data_platform import research_iv_artifact_files as files_api
    from nse_quant.data_platform import research_iv_bundle as codec
    from nse_quant.data_platform.audit import AuditLedger

    if (
        native.VERSION != "native-research-iv-artifact-materialization@1"
        or files_api.VERSION != "research-iv-artifact-files@1"
        or codec.VERSION != "research-iv-feature-bundle@1"
    ):
        raise ValueError("UNSUPPORTED_IV_FIRST_STAGE_DEPENDENCY_VERSION")
    pins = (
        build_id_pin,
        expected_archive_fingerprint,
        expected_bundle_id,
        expected_revalidation_fingerprint,
    )
    group = scope(pins, str(artifact_root))
    if (
        type(initialize) is not bool
        or type(initialize_artifacts) is not bool
        or not _identifier(actor_id)
        or not _identifier(code_revision)
    ):
        raise ValueError("IV_FIRST_STAGE_EXECUTION_IDENTIFIERS_REQUIRED")
    files = files_api.ResearchIvArtifactFiles(artifact_root)
    files._parents()
    _owned(target)
    targets = _paths(target)
    inputs = (
        bronze,
        frame_silver,
        reference_silver,
        assessments,
        source_gold,
        archive,
        bundle_archive,
    )
    for source in inputs:
        if source is target or any(
            a == b or a.samefile(b) for a in targets for b in _paths(source)
        ):
            raise ValueError("SEPARATE_IV_FIRST_STAGE_DATABASE_REQUIRED")
    output = artifact_root.resolve()
    databases = [path for conn in (*inputs, target) for path in _paths(conn)]
    for path in databases:
        path = path.resolve()
        if output == path or output in path.parents or path in output.parents:
            raise ValueError("IV_STAGE_ARTIFACT_ROOT_DATABASE_OVERLAP")
    if artifact_root.exists():
        files._root()
        if any(child.samefile(path) for child in artifact_root.iterdir() for path in databases):
            raise ValueError("IV_STAGE_ARTIFACT_DATABASE_HARDLINK")
    if initialize:
        _initialize(target)
    rows, _ = _transaction_snapshot(target)
    if rows:
        raise IvFirstStageReviewRequired("IV_FIRST_STAGE_EXISTS_NO_RETRY_PROFILE")
    ledger = AuditLedger(target)
    job = ledger.plan_job(
        command_name=COMMAND,
        actor_id=actor_id,
        code_revision=code_revision,
        scope_ref=group,
        config_hash=sha(canonical(DEFINITION).encode()),
    )
    with ledger.execution(job):
        observed = native.materialize_research_iv_artifact(
            *inputs,
            build_id_pin=build_id_pin,
            expected_archive_fingerprint=expected_archive_fingerprint,
            expected_bundle_id=expected_bundle_id,
            expected_revalidation_fingerprint=expected_revalidation_fingerprint,
            artifact_root=artifact_root,
            initialize=initialize_artifacts,
        )
        if type(observed) is not native.ResearchIvArtifactMaterialization:
            raise ValueError("IV_FIRST_STAGE_TYPED_MATERIALIZATION_REQUIRED")
        if observed.status != "materialized_research_iv_artifact_not_staged":
            raise IvFirstStageNativeRejected(observed)
        if (
            observed.artifact_written is not True
            or observed.artifact_bytes_rechecked is not True
            or observed.audited_stage_recorded is not False
            or observed.after is None
            or any(getattr(observed, key) is not False for key in FLAGS)
            or observed.canonical_contract_id is not None
            or observed.event_ts is not None
            or observed.published_at is not None
            or (
                observed.archive_record_id,
                observed.expected_archive_fingerprint,
                observed.expected_bundle_id,
                observed.expected_revalidation_fingerprint,
            )
            != pins
            or asdict(observed.before) != asdict(observed.after)
            or observed.before.evidence_fingerprint != expected_revalidation_fingerprint
            or observed.before.bundle_id != expected_bundle_id
        ):
            raise ValueError("IV_FIRST_STAGE_MATERIALIZATION_CONTRACT_MISMATCH")
        raw = files.read_exact(expected_bundle_id)
        codec.decode_research_iv_bundle(raw, expected_bundle_id=expected_bundle_id)
        body = dict(
            version="research-iv-first-stage-record@1",
            definition=list(DEFINITION),
            pins=list(pins),
            artifact_root=str(artifact_root),
            artifact_name=files.path(expected_bundle_id).name,
            artifact_bytes=len(raw),
            before_sha256=sha(canonical(asdict(observed.before)).encode()),
            after_sha256=sha(canonical(asdict(observed.after)).encode()),
            status="RESEARCH_IV_STAGE_RECORDED_NOT_PUBLISHED",
            canonical_contract_id=None,
            event_ts=None,
            published_at=None,
            **{key: False for key in FLAGS},
        )
        record_json = canonical(body)
        key = build_id(record_json)
        target.execute("BEGIN TRANSACTION")
        try:
            prior, _ = _snapshot(target, active_job=job, active_scope=group)
            if prior:
                raise IvFirstStageReviewRequired("IV_FIRST_STAGE_CONCURRENT_RECORD")
            ledger.register_contract(_contract())
            target.execute(
                f"INSERT INTO {_name(target, 'gold', TABLES[1])} VALUES (?,?,?,?,?,?,?,?)",
                [key, group, record_json, FEATURE, job, datetime.now(UTC), None, None],
            )
            target.execute(
                f"INSERT INTO {_name(target, 'gold', TABLES[2])} VALUES (?,?,?)",
                [job, group, key],
            )
            target.execute("COMMIT")
        except BaseException:
            target.execute("ROLLBACK")
            raise
    return {
        "build_id": key,
        "job_id": job,
        "status": body["status"],
        "audited_stage_recorded": True,
        "publication_asserted": False,
        "decision_eligibility_asserted": False,
    }


def read_research_iv_first_stage(
    target: Any,
    *,
    build_id_pin: str,
    artifact_root: Path,
) -> ResearchIvFirstStage:
    """Original stage/audit/artifact check only; no initialization or current sources."""
    from nse_quant.data_platform import research_iv_artifact_files as files_api
    from nse_quant.data_platform import research_iv_bundle as codec

    if files_api.VERSION != "research-iv-artifact-files@1":
        raise ValueError("IV_FIRST_STAGE_FILE_API_VERSION_UNSUPPORTED")
    if not pin(build_id_pin) or codec.VERSION != "research-iv-feature-bundle@1":
        raise ValueError("IV_FIRST_STAGE_EXACT_PIN_AND_SUPPORTED_CODEC_REQUIRED")
    before, fingerprint = _transaction_snapshot(target)
    if len(before) != 1 or before[0][0] != build_id_pin:
        raise IvFirstStageReviewRequired("IV_FIRST_STAGE_EXACT_RECORD_NOT_FOUND")
    record_json = before[0][2]
    parsed = decode(record_json)
    if str(artifact_root) != parsed["artifact_root"]:
        raise IvFirstStageReviewRequired("IV_FIRST_STAGE_ROOT_PIN_MISMATCH")
    files = files_api.ResearchIvArtifactFiles(artifact_root)
    raw = files.read_exact(parsed["pins"][2])
    codec.decode_research_iv_bundle(raw, expected_bundle_id=parsed["pins"][2])
    if len(raw) != parsed["artifact_bytes"]:
        raise IvFirstStageReviewRequired("IV_FIRST_STAGE_ARTIFACT_BYTES_MISMATCH")
    after, later = _transaction_snapshot(target)
    if before != after or fingerprint != later or files.read_exact(parsed["pins"][2]) != raw:
        raise IvFirstStageReviewRequired("IV_FIRST_STAGE_HISTORY_OR_ARTIFACT_CHANGED")
    return ResearchIvFirstStage(
        VERSION,
        build_id_pin,
        "verified_research_stage_recording",
        record_json,
        sha(canonical([VERSION, build_id_pin, fingerprint, sha(raw)]).encode()),
    )
