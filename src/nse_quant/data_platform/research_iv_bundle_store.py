"""Dedicated audited research-IV bundle archive; never publication or admission."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from nse_quant.data_platform.research_iv_bundle_archive_record import (
    ASSEMBLY_VERSION,
    MAX_REQUEST_BYTES,
    MAX_RESULT_BYTES,
    canonical,
    pin,
    prior_links,
    record_id,
    requests_value,
    result_value,
    scope_id,
    sha,
)

if TYPE_CHECKING:
    from nse_quant.data_platform.native_research_iv_bundle import IvBundleRequest

VERSION = "audited-research-iv-bundles@1"
FEATURE_VERSION = "research-iv-bundle-archive@1"
COMMAND = "archive.research_iv_bundle@1"
MAX_BUILDS = 256
MAX_JOBS = 1000
MAX_SCOPE_BYTES = 67108864
DOMAIN_TABLES = (
    "research_iv_bundle_schema_versions",
    "research_iv_bundle_definitions",
    "research_iv_bundle_builds",
    "research_iv_bundle_attempts",
)


class IvBundleArchiveReviewRequired(ValueError):
    """Full original recording obligations are incomplete; no old-good fallback."""


@dataclass(frozen=True)
class ResearchIvBundleArchive:
    version: str
    build_id: str
    input_id: str
    status: str
    retained_head_build_id: str
    recorded_result_status: str
    requests_json: str
    result_json: str
    evidence_fingerprint: str
    archived_recording_verified: bool = True
    current_source_checked: bool = False
    publication_asserted: bool = False
    decision_eligibility_asserted: bool = False
    canonical_contract_id: None = None


def _name(conn: Any, schema: str, table: str) -> str:
    row = conn.execute("SELECT current_database()").fetchone()
    if row is None:
        raise ValueError("IV_BUNDLE_ARCHIVE_CATALOG_REQUIRED")
    return ".".join('"' + str(x).replace('"', '""') + '"' for x in (row[0], schema, table))


def _paths(conn: Any) -> tuple[Path, ...]:
    return tuple(Path(row[2]) for row in conn.execute("PRAGMA database_list").fetchall() if row[2])


def _owned(conn: Any) -> None:
    row = conn.execute("SELECT current_database()").fetchone()
    if row is None or not any(
        item[1] == row[0] and item[2] for item in conn.execute("PRAGMA database_list").fetchall()
    ):
        raise ValueError("FILE_BACKED_IV_BUNDLE_ARCHIVE_REQUIRED")
    allowed = {("gold", name) for name in DOMAIN_TABLES} | {
        ("medallion_audit", name)
        for name in ("schema_versions", "dataset_contracts", "jobs", "job_events")
    }
    rows = conn.execute(
        "SELECT table_schema,table_name FROM information_schema.tables "
        "WHERE table_catalog=current_database()"
    ).fetchall()
    if any(tuple(item) not in allowed for item in rows):
        raise ValueError("DEDICATED_IV_BUNDLE_ARCHIVE_REQUIRED")


def _contract() -> Any:
    from nse_quant.data_platform.contracts import DatasetContract, Layer, WritePolicy

    return DatasetContract(
        "gold.research_iv_bundle_builds",
        "1",
        Layer.GOLD,
        WritePolicy.VERSIONED_BUILDS,
        ("build_id",),
        ("build_id", "event_ts", "published_at", "feature_version"),
        "native_research_iv_bundle_archive",
    )


def _definition() -> str:
    return canonical(
        [
            VERSION,
            FEATURE_VERSION,
            ASSEMBLY_VERSION,
            "research-iv-feature-bundle@1",
            "research-iv-current-source-revalidation@1",
            "audited-research-iv-builds@1",
            "research-iv-bundle-archive-record@1",
            MAX_RESULT_BYTES,
            MAX_REQUEST_BYTES,
            "research-only-recording-not-current-source-verification@1",
        ]
    )


def _initialize(conn: Any) -> None:
    from nse_quant.data_platform.audit import AuditLedger

    _owned(conn)
    AuditLedger(conn).initialize()
    conn.execute("BEGIN TRANSACTION")
    try:
        conn.execute('CREATE SCHEMA IF NOT EXISTS "gold"')
        table = _name(conn, "gold", DOMAIN_TABLES[0])
        conn.execute(f"CREATE TABLE IF NOT EXISTS {table} (version INTEGER PRIMARY KEY)")
        versions = conn.execute(f"SELECT version FROM {table} LIMIT 2").fetchall()
        if versions and versions != [(1,)]:
            raise ValueError("IV_BUNDLE_ARCHIVE_SCHEMA_UNSUPPORTED")
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS {_name(conn, 'gold', DOMAIN_TABLES[1])} ("
            "feature_version VARCHAR PRIMARY KEY,definition_json VARCHAR NOT NULL,"
            "definition_hash VARCHAR NOT NULL,first_job_id VARCHAR NOT NULL,"
            "recorded_at TIMESTAMPTZ NOT NULL)"
        )
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS {_name(conn, 'gold', DOMAIN_TABLES[2])} ("
            "build_id VARCHAR PRIMARY KEY,input_id VARCHAR NOT NULL,ordinal INTEGER NOT NULL,"
            "feature_version VARCHAR NOT NULL,definition_hash VARCHAR NOT NULL,"
            "requests_json VARCHAR NOT NULL,result_json VARCHAR NOT NULL,"
            "prior_ids_json VARCHAR NOT NULL,first_job_id VARCHAR NOT NULL,"
            "recorded_at TIMESTAMPTZ NOT NULL,event_ts TIMESTAMPTZ,published_at TIMESTAMPTZ,"
            "UNIQUE(input_id,ordinal))"
        )
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS {_name(conn, 'gold', DOMAIN_TABLES[3])} ("
            "job_id VARCHAR PRIMARY KEY,input_id VARCHAR NOT NULL,build_id VARCHAR NOT NULL)"
        )
        if not versions:
            if any(
                conn.execute(f"SELECT 1 FROM {_name(conn, 'gold', name)} LIMIT 1").fetchone()
                for name in DOMAIN_TABLES[1:]
            ):
                raise ValueError("IV_BUNDLE_ARCHIVE_PARTIAL_SCHEMA_NOT_ADOPTABLE")
            conn.execute(f"INSERT INTO {table} VALUES (1)")
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def _instant(value: object) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise IvBundleArchiveReviewRequired("IV_BUNDLE_ARCHIVE_AWARE_CLOCK_REQUIRED")
    return value.astimezone(UTC).isoformat()


def _scope(
    conn: Any,
    group: str,
    definition_hash: str,
    active_job: str | None = None,
) -> tuple[list[tuple[Any, ...]], str]:
    budget = conn.execute(
        "SELECT coalesce(sum(octet_length(encode(requests_json)) + "
        "octet_length(encode(result_json)) + octet_length(encode(prior_ids_json))),0) "
        f"FROM {_name(conn, 'gold', DOMAIN_TABLES[2])} WHERE input_id=?",
        [group],
    ).fetchone()
    if budget is None or budget[0] > MAX_SCOPE_BYTES:
        raise IvBundleArchiveReviewRequired("IV_BUNDLE_ARCHIVE_SCOPE_BYTE_LIMIT")
    rows = conn.execute(
        f"SELECT build_id,input_id,ordinal,feature_version,definition_hash,"
        "CASE WHEN octet_length(encode(requests_json))<=? THEN requests_json END,"
        "CASE WHEN octet_length(encode(result_json))<=? THEN result_json END,"
        "CASE WHEN octet_length(encode(prior_ids_json))<=32768 THEN prior_ids_json END,"
        f"first_job_id,recorded_at,event_ts,published_at FROM "
        f"{_name(conn, 'gold', DOMAIN_TABLES[2])} WHERE input_id=? ORDER BY ordinal LIMIT ?",
        [MAX_REQUEST_BYTES, MAX_RESULT_BYTES, group, MAX_BUILDS + 1],
    ).fetchall()
    attempts = conn.execute(
        f"SELECT job_id,build_id FROM {_name(conn, 'gold', DOMAIN_TABLES[3])} "
        "WHERE input_id=? ORDER BY job_id LIMIT ?",
        [group, MAX_JOBS + 1],
    ).fetchall()
    jobs = conn.execute(
        f"SELECT job_id,parent_job_id,command_name,config_hash,created_at,actor_id,code_revision "
        f"FROM {_name(conn, 'medallion_audit', 'jobs')} "
        "WHERE scope_ref=? ORDER BY job_id LIMIT ?",
        [group, MAX_JOBS + 1],
    ).fetchall()
    if len(rows) > MAX_BUILDS or len(attempts) > MAX_JOBS or len(jobs) > MAX_JOBS:
        raise IvBundleArchiveReviewRequired("IV_BUNDLE_ARCHIVE_HISTORY_LIMIT")
    ids: list[str] = []
    origins: dict[str, str] = {}
    normalized: list[object] = []
    for index, row in enumerate(rows, 1):
        key, scope, ordinal, feature, definition, requests, result, links, origin, clock = row[:10]
        if (
            scope != group
            or type(ordinal) is not int
            or ordinal != index
            or feature != FEATURE_VERSION
            or definition != definition_hash
            or scope_id(requests, definition) != group
            or record_id(group, result, requests) != key
            or key in ids
            or row[10:] != (None, None)
        ):
            raise IvBundleArchiveReviewRequired("IV_BUNDLE_ARCHIVE_RECORD_MISMATCH")
        prior_links(links, tuple(ids))
        ids.append(key)
        origins[key] = origin
        normalized.append([*row[:9], _instant(clock), None, None])
    links_by_job = dict(attempts)
    if len(links_by_job) != len(attempts) or any(
        key not in origins for key in links_by_job.values()
    ):
        raise IvBundleArchiveReviewRequired("IV_BUNDLE_ARCHIVE_ATTEMPT_LINK_INVALID")
    audit: list[object] = []
    for job, parent, command, config, created, actor, revision in jobs:
        events = conn.execute(
            f"SELECT event_index,state,recorded_at,reason_code FROM "
            f"{_name(conn, 'medallion_audit', 'job_events')} "
            "WHERE job_id=? ORDER BY event_index LIMIT 7",
            [job],
        ).fetchall()
        expected = (
            ("PLANNED", "RUNNING") if job == active_job else ("PLANNED", "RUNNING", "SUCCEEDED")
        )
        if (
            parent is not None
            or command != COMMAND
            or config != definition_hash
            or any(type(item[0]) is not int for item in events)
            or tuple(item[0] for item in events) != tuple(range(1, len(expected) + 1))
            or tuple(item[1] for item in events) != expected
            or any(item[3] is not None for item in events)
            or any(not _identifier(item) for item in (actor, revision))
            or job != active_job
            and job not in links_by_job
        ):
            raise IvBundleArchiveReviewRequired("IV_BUNDLE_ARCHIVE_INCOMPLETE_AUDIT_OBLIGATION")
        audit.append(
            [
                job,
                parent,
                command,
                config,
                _instant(created),
                actor,
                revision,
                [[item[0], item[1], _instant(item[2]), item[3]] for item in events],
            ]
        )
    job_ids = {row[0] for row in jobs}
    if (
        active_job is not None
        and active_job not in job_ids
        or any(job not in job_ids for job in links_by_job)
        or any(links_by_job.get(job) != key for key, job in origins.items())
    ):
        raise IvBundleArchiveReviewRequired("IV_BUNDLE_ARCHIVE_ORIGIN_NOT_LINKED")
    return rows, sha(canonical([VERSION, group, normalized, attempts, audit]).encode())


def _identifier(value: object) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value) <= 256
        and value == value.strip()
        and all(ord(char) >= 32 for char in value)
    )


def _global(
    conn: Any,
    *,
    allow_empty: bool = False,
    active_job: str | None = None,
    active_scope: str | None = None,
) -> str | None:
    _owned(conn)
    for schema, table in (("gold", DOMAIN_TABLES[0]), ("medallion_audit", "schema_versions")):
        if conn.execute(f"SELECT version FROM {_name(conn, schema, table)} LIMIT 2").fetchall() != [
            (1,),
        ]:
            raise IvBundleArchiveReviewRequired("IV_BUNDLE_ARCHIVE_SCHEMA_UNSUPPORTED")
    definitions = conn.execute(
        "SELECT feature_version,CASE WHEN octet_length(encode(definition_json))<=32768 "
        "THEN definition_json END,definition_hash,first_job_id,recorded_at FROM "
        f"{_name(conn, 'gold', DOMAIN_TABLES[1])} LIMIT 2"
    ).fetchall()
    contract = _contract()
    registered = conn.execute(
        "SELECT fingerprint,CASE WHEN octet_length(encode(contract_json))<=32768 "
        "THEN contract_json END,registered_at FROM "
        f"{_name(conn, 'medallion_audit', 'dataset_contracts')} "
        "WHERE dataset_name=? AND contract_version='1' LIMIT 2",
        [contract.name],
    ).fetchall()
    if not definitions and allow_empty:
        if registered or any(
            conn.execute(f"SELECT 1 FROM {_name(conn, 'gold', name)} LIMIT 1").fetchone()
            for name in DOMAIN_TABLES[2:]
        ):
            raise IvBundleArchiveReviewRequired("IV_BUNDLE_ARCHIVE_ORPHAN_DOMAIN")
        return None
    definition = _definition()
    if (
        len(definitions) != 1
        or definitions[0][:3] != (FEATURE_VERSION, definition, sha(definition.encode()))
        or len(registered) != 1
        or registered[0][:2] != (contract.fingerprint, contract.canonical_json())
    ):
        raise IvBundleArchiveReviewRequired("IV_BUNDLE_ARCHIVE_DEFINITION_CONTRACT_MISMATCH")
    origin = definitions[0][3]
    links = conn.execute(
        f"SELECT input_id,build_id FROM {_name(conn, 'gold', DOMAIN_TABLES[3])} "
        "WHERE job_id=? LIMIT 2",
        [origin],
    ).fetchall()
    if len(links) != 1:
        raise IvBundleArchiveReviewRequired("IV_BUNDLE_ARCHIVE_DEFINITION_ORIGIN_MISSING")
    origin_scope = links[0][0]
    rows, fingerprint = _scope(
        conn,
        origin_scope,
        sha(definition.encode()),
        active_job if origin_scope == active_scope else None,
    )
    if not any(row[0] == links[0][1] and row[8] == origin for row in rows):
        raise IvBundleArchiveReviewRequired("IV_BUNDLE_ARCHIVE_DEFINITION_NOT_OWN_ORIGIN")
    return sha(
        canonical(
            [
                VERSION,
                definitions[0][:4],
                _instant(definitions[0][4]),
                registered[0][:2],
                _instant(registered[0][2]),
                links,
                fingerprint,
            ]
        ).encode()
    )


def persist_research_iv_bundle(
    bronze: Any,
    frame_silver: Any,
    reference_silver: Any,
    assessments: Any,
    source_gold: Any,
    archive: Any,
    target: Any,
    *,
    requests: tuple[IvBundleRequest, ...],
    actor_id: str,
    code_revision: str,
    initialize: bool = False,
) -> dict[str, object]:
    from nse_quant.data_platform import native_research_iv_bundle as native
    from nse_quant.data_platform import research_iv_bundle as codec
    from nse_quant.data_platform.audit import AuditLedger

    if native.VERSION != ASSEMBLY_VERSION or codec.VERSION != "research-iv-feature-bundle@1":
        raise ValueError("IV_BUNDLE_ARCHIVE_DEPENDENCY_VERSION_UNSUPPORTED")
    if type(initialize) is not bool or not all(_identifier(x) for x in (actor_id, code_revision)):
        raise ValueError("IV_BUNDLE_ARCHIVE_EXECUTION_IDENTIFIERS_REQUIRED")
    if type(requests) is not tuple or not 1 <= len(requests) <= 64:
        raise ValueError("IV_BUNDLE_ARCHIVE_BOUNDED_REQUESTS_REQUIRED")
    if any(type(item) is not native.IvBundleRequest for item in requests):
        raise TypeError("IV_BUNDLE_ARCHIVE_TYPED_REQUESTS_REQUIRED")
    ordered = tuple(
        sorted(
            (
                native.IvBundleRequest(
                    item.build_id,
                    item.expected_archive_fingerprint,
                )
                for item in requests
            ),
            key=lambda item: item.build_id,
        )
    )
    requests_json = canonical([asdict(item) for item in ordered])
    requests_value(requests_json)
    definition = _definition()
    definition_hash = sha(definition.encode())
    group = scope_id(requests_json, definition_hash)
    _owned(target)
    output_paths = _paths(target)
    for source in (bronze, frame_silver, reference_silver, assessments, source_gold, archive):
        if source is target or any(
            a == b or a.samefile(b) for a in output_paths for b in _paths(source)
        ):
            raise ValueError("SEPARATE_IV_BUNDLE_ARCHIVE_OUTPUT_REQUIRED")
    if initialize:
        _initialize(target)
    target.execute("BEGIN TRANSACTION")
    try:
        _global(target, allow_empty=True)
        _scope(target, group, definition_hash)
        target.execute("COMMIT")
    except BaseException:
        target.execute("ROLLBACK")
        raise
    ledger = AuditLedger(target)
    job = ledger.plan_job(
        command_name=COMMAND,
        actor_id=actor_id,
        code_revision=code_revision,
        scope_ref=group,
        config_hash=definition_hash,
    )
    with ledger.execution(job):
        assembled = native.assemble_native_research_iv_bundle(
            bronze,
            frame_silver,
            reference_silver,
            assessments,
            source_gold,
            archive,
            requests=ordered,
        )
        if type(assembled) is not native.NativeIvBundleAssembly:
            raise ValueError("IV_BUNDLE_ARCHIVE_NATIVE_RESULT_TYPE_REQUIRED")
        result_json = canonical(asdict(assembled))
        key = record_id(group, result_json, requests_json)
        target.execute("BEGIN TRANSACTION")
        try:
            _global(target, allow_empty=True, active_job=job, active_scope=group)
            rows, _ = _scope(target, group, definition_hash, job)
            ledger.register_contract(_contract())
            table = _name(target, "gold", DOMAIN_TABLES[1])
            definitions = target.execute(
                f"SELECT definition_json,definition_hash FROM {table} LIMIT 2"
            ).fetchall()
            if not definitions:
                target.execute(
                    f"INSERT INTO {table} VALUES (?,?,?,?,?)",
                    [
                        FEATURE_VERSION,
                        definition,
                        definition_hash,
                        job,
                        datetime.now(UTC),
                    ],
                )
            elif definitions != [(definition, definition_hash)]:
                raise ValueError("IV_BUNDLE_ARCHIVE_DEFINITION_CHANGED")
            prior = next((row for row in rows if row[0] == key), None)
            inserted = prior is None
            if prior is not None:
                if prior[5:7] != (requests_json, result_json):
                    raise ValueError("IV_BUNDLE_ARCHIVE_RETRY_CONTENT_MISMATCH")
            else:
                if len(rows) >= MAX_BUILDS:
                    raise ValueError("IV_BUNDLE_ARCHIVE_BUILD_LIMIT")
                links_json = canonical([row[0] for row in rows])
                retained_bytes = sum(
                    len(str(row[index]).encode()) for row in rows for index in (5, 6, 7)
                )
                if (
                    retained_bytes
                    + sum(
                        len(x.encode())
                        for x in (
                            requests_json,
                            result_json,
                            links_json,
                        )
                    )
                    > MAX_SCOPE_BYTES
                ):
                    raise ValueError("IV_BUNDLE_ARCHIVE_SCOPE_BYTE_LIMIT")
                target.execute(
                    f"INSERT INTO {_name(target, 'gold', DOMAIN_TABLES[2])} "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    [
                        key,
                        group,
                        len(rows) + 1,
                        FEATURE_VERSION,
                        definition_hash,
                        requests_json,
                        result_json,
                        links_json,
                        job,
                        datetime.now(UTC),
                        None,
                        None,
                    ],
                )
            target.execute(
                f"INSERT INTO {_name(target, 'gold', DOMAIN_TABLES[3])} VALUES (?,?,?)",
                [job, group, key],
            )
            target.execute("COMMIT")
        except BaseException:
            target.execute("ROLLBACK")
            raise
    return {
        "build_id": key,
        "input_id": group,
        "job_id": job,
        "inserted": inserted,
        "status": assembled.status,
        "publication_asserted": False,
        "decision_eligibility_asserted": False,
    }


def read_research_iv_bundle_archive(target: Any, *, build_id_pin: str) -> ResearchIvBundleArchive:
    """Read only: verifies retained archive/audit, NOT current member/source truth."""
    if not pin(build_id_pin):
        raise ValueError("IV_BUNDLE_ARCHIVE_EXACT_BUILD_PIN_REQUIRED")
    target.execute("BEGIN TRANSACTION")
    try:
        global_fingerprint = _global(target)
        found = target.execute(
            f"SELECT input_id FROM {_name(target, 'gold', DOMAIN_TABLES[2])} "
            "WHERE build_id=? LIMIT 2",
            [build_id_pin],
        ).fetchall()
        if len(found) != 1:
            raise IvBundleArchiveReviewRequired("IV_BUNDLE_ARCHIVE_EXACT_PIN_NOT_FOUND")
        rows, scope_fingerprint = _scope(target, found[0][0], sha(_definition().encode()))
        selected = next(row for row in rows if row[0] == build_id_pin)
        fingerprint = sha(canonical([VERSION, global_fingerprint, scope_fingerprint]).encode())
        recorded_status = result_value(selected[6], selected[5])["status"]
        head = rows[-1][0]
        target.execute("COMMIT")
    except BaseException:
        target.execute("ROLLBACK")
        raise
    return ResearchIvBundleArchive(
        VERSION,
        build_id_pin,
        found[0][0],
        "verified_archived_head" if head == build_id_pin else "review_required",
        head,
        recorded_status,
        selected[5],
        selected[6],
        fingerprint,
    )
