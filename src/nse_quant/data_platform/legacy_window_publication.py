"""Audited native research publication profile for full return-window bundles."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from nse_quant.data_platform import legacy_market_publication as native
from nse_quant.data_platform import legacy_window_bundle as bundle
from nse_quant.data_platform.audit import AuditLedger, JobState
from nse_quant.data_platform.contracts import DatasetContract, Layer, WritePolicy

VERSION = "legacy-window-research-publication@1"
POLICY_VERSION = "legacy-window-research-only-policy@1"
COMMAND = "publish.legacy_window_research_bundle@1"
PURPOSE = "RESEARCH_ONLY"
CLOCK = native.CLOCK
DOMAIN = ("window_publication_versions", "window_publications", "window_publication_attempts")
TABLES = {("gold", n) for n in DOMAIN} | {
    ("medallion_audit", n) for n in ("schema_versions", "dataset_contracts", "jobs", "job_events")
}
CONTRACT = DatasetContract(
    "gold.window_research_publications",
    "1",
    Layer.GOLD,
    WritePolicy.VERSIONED_BUILDS,
    ("build_id",),
    ("build_id", "event_ts", "published_at", "feature_version"),
    "native_window_research_publication",
)
name = native.name


def _definition() -> bytes:
    return bundle.canonical(
        [
            VERSION,
            POLICY_VERSION,
            bundle.VERSION,
            CONTRACT.canonical_json(),
            bundle.source._definition().hex(),
            bundle.MAX_BYTES,
            CLOCK,
            "whole source window recording, no selection or pin-based original-obligation healing",
            "research-only record clocks are not provider availability/economic validity",
        ]
    )


def scope_id(window_build_id: str) -> str:
    if not bundle.pin(window_build_id):
        raise ValueError("EXACT_WINDOW_PUBLICATION_SOURCE_REQUIRED")
    return native._hash([VERSION, window_build_id])


def publication_id(window_build_id: str, bundle_id: str) -> str:
    if not bundle.pin(bundle_id):
        raise ValueError("EXACT_WINDOW_PUBLICATION_BUNDLE_REQUIRED")
    return native._hash([VERSION, POLICY_VERSION, scope_id(window_build_id), bundle_id, PURPOSE])


def _owned(c: Any, *, complete: bool) -> None:
    paths = c.execute(
        "SELECT path FROM duckdb_databases() WHERE database_name=current_database()"
    ).fetchall()
    if len(paths) != 1 or not paths[0][0]:
        raise ValueError("FILE_BACKED_WINDOW_PUBLICATION_REQUIRED")
    rows = c.execute(
        "SELECT table_schema,table_name,table_type FROM information_schema.tables "
        "WHERE table_catalog=current_database() ORDER BY table_schema,table_name LIMIT 8"
    ).fetchall()
    known = {(s, t) for s, t, _ in rows}
    if known - TABLES or any(k != "BASE TABLE" for _, _, k in rows) or complete and known != TABLES:
        raise ValueError("DEDICATED_WINDOW_PUBLICATION_REQUIRED")


def initialize_window_publication(c: Any) -> None:
    _owned(c, complete=False)
    if c.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_catalog=current_database() LIMIT 1"
    ).fetchone():
        raise ValueError("EMPTY_WINDOW_PUBLICATION_INITIALIZATION_REQUIRED")
    AuditLedger(c).initialize()
    versions, records, attempts = (name(c, "gold", n) for n in DOMAIN)
    c.execute("BEGIN TRANSACTION")
    try:
        c.execute(f"CREATE SCHEMA {versions.rsplit('.', 1)[0]}")
        c.execute(f"CREATE TABLE {versions} (version INTEGER PRIMARY KEY,definition BLOB)")
        c.execute(f"INSERT INTO {versions} VALUES (1,?)", [_definition()])
        c.execute(f"""CREATE TABLE {records} (
            build_id VARCHAR PRIMARY KEY,scope_id VARCHAR UNIQUE NOT NULL,
            window_build_id VARCHAR UNIQUE NOT NULL,request_bytes BLOB NOT NULL,
            bundle_id VARCHAR NOT NULL,manifest_bytes BLOB NOT NULL,
            manifest_byte_count BIGINT NOT NULL,row_count INTEGER NOT NULL,
            policy_bytes BLOB NOT NULL,feature_version VARCHAR NOT NULL,purpose VARCHAR NOT NULL,
            clock_semantics VARCHAR NOT NULL,event_ts TIMESTAMPTZ,published_at TIMESTAMPTZ NOT NULL,
            effective_from TIMESTAMPTZ,effective_to TIMESTAMPTZ,
            decision_eligibility_asserted BOOLEAN NOT NULL,first_job_id VARCHAR NOT NULL)""")
        c.execute(f"""CREATE TABLE {attempts} (
            job_id VARCHAR PRIMARY KEY,scope_id VARCHAR NOT NULL,
            window_build_id VARCHAR NOT NULL,build_id VARCHAR NOT NULL)""")
        c.execute("COMMIT")
    except BaseException:
        c.execute("ROLLBACK")
        raise
    AuditLedger(c).register_contract(CONTRACT)


def _schema(c: Any) -> None:
    _owned(c, complete=True)
    if c.execute(
        f"SELECT version,CASE WHEN octet_length(definition)<=32768 THEN definition END "
        f"FROM {name(c, 'gold', DOMAIN[0])} LIMIT 2"
    ).fetchall() != [(1, _definition())]:
        raise ValueError("WINDOW_PUBLICATION_DEFINITION_DRIFT")
    if c.execute(
        f"SELECT fingerprint,CASE WHEN octet_length(encode(contract_json))<=32768 "
        f"THEN contract_json END FROM {name(c, 'medallion_audit', 'dataset_contracts')} "
        "WHERE dataset_name=? AND contract_version='1'",
        [CONTRACT.name],
    ).fetchall() != [(CONTRACT.fingerprint, CONTRACT.canonical_json())]:
        raise ValueError("WINDOW_PUBLICATION_CONTRACT_DRIFT")
    if c.execute(
        f"SELECT version FROM {name(c, 'medallion_audit', 'schema_versions')} LIMIT 2"
    ).fetchall() != [(1,)]:
        raise ValueError("WINDOW_PUBLICATION_AUDIT_SCHEMA_DRIFT")


def _config(request: bundle.WindowBundleRequest, reviewed_bundle_id: str) -> str:
    return native._hash([_definition().hex(), asdict(request), reviewed_bundle_id])


def _unused(c: Any, request: bundle.WindowBundleRequest) -> None:
    scope = scope_id(request.build_id)
    for n in DOMAIN[1:]:
        if c.execute(
            f"SELECT 1 FROM {name(c, 'gold', n)} WHERE scope_id=? OR window_build_id=? LIMIT 1",
            [scope, request.build_id],
        ).fetchone():
            raise ValueError("WINDOW_PUBLICATION_FIRST_WRITE_OR_ORPHAN_OBLIGATION")
    if c.execute(
        f"SELECT 1 FROM {name(c, 'medallion_audit', 'jobs')} WHERE scope_ref=? LIMIT 1",
        ["sha256:" + scope],
    ).fetchone():
        raise ValueError("WINDOW_PUBLICATION_FIRST_WRITE_ORIGINAL_AUDIT_OBLIGATION")


def publish_window_research_bundle(
    bronze: Any,
    silver: Any,
    geometry: Any,
    returns: Any,
    windows: Any,
    target: Any,
    *,
    request: bundle.WindowBundleRequest,
    expected_bundle_id: str,
    actor_id: str,
    code_revision: str,
    purpose: str,
    allow_research_publication: bool = False,
) -> dict[str, Any]:
    """Intent gate is not authorization; disposable synthetic research use only is released."""
    if allow_research_publication is not True or purpose != PURPOSE:
        raise ValueError("EXPLICIT_WINDOW_RESEARCH_PUBLICATION_REQUIRED")
    if type(request) is not bundle.WindowBundleRequest:
        raise TypeError("TYPED_WINDOW_PUBLICATION_REQUEST_REQUIRED")
    request = bundle.WindowBundleRequest(**asdict(request))
    if (
        not bundle.pin(expected_bundle_id)
        or not native._identifier(actor_id)
        or type(code_revision) is not str
        or re.fullmatch(r"[a-f0-9]{40}", code_revision) is None
    ):
        raise ValueError("EXACT_WINDOW_PUBLICATION_REVIEW_AND_EXECUTION_PINS_REQUIRED")
    sources = (bronze, silver, geometry, returns, windows)
    for c in sources:
        native.foundation._separate(c, target)
    _schema(target)
    _unused(target, request)
    scope = scope_id(request.build_id)
    key = publication_id(request.build_id, expected_bundle_id)
    ledger = AuditLedger(target)
    job = ledger.plan_job(
        command_name=COMMAND,
        actor_id=actor_id,
        code_revision=code_revision,
        scope_ref="sha256:" + scope,
        config_hash=_config(request, expected_bundle_id),
    )
    with ledger.execution(job):
        raw = bundle.assemble_window_bundle(*sources, request=request)
        if bundle.sha(raw) != expected_bundle_id:
            raise ValueError("WINDOW_PUBLICATION_REVIEWED_BUNDLE_CHANGED")
        ledger.transition(job, JobState.STAGED)
        if bundle.assemble_window_bundle(*sources, request=request) != raw:
            raise ValueError("WINDOW_PUBLICATION_COMPLETE_NATIVE_SOURCE_DRIFT")
        bundle.replay_window_bundle(raw, expected_bundle_id=expected_bundle_id)
        doc = json.loads(raw)
        ledger.transition(job, JobState.VALIDATED)
        at = datetime.now(UTC)
        target.execute("BEGIN TRANSACTION")
        try:
            target.execute(
                f"INSERT INTO {name(target, 'gold', DOMAIN[1])} "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [
                    key,
                    scope,
                    request.build_id,
                    bundle.canonical(asdict(request)),
                    expected_bundle_id,
                    raw,
                    len(raw),
                    len(doc["outputs"]),
                    bundle.canonical(doc["policy"]),
                    VERSION,
                    PURPOSE,
                    CLOCK,
                    None,
                    at,
                    None,
                    None,
                    False,
                    job,
                ],
            )
            target.execute(
                f"INSERT INTO {name(target, 'gold', DOMAIN[2])} VALUES (?,?,?,?)",
                [job, scope, request.build_id, key],
            )
            target.execute("COMMIT")
        except BaseException:
            target.execute("ROLLBACK")
            raise
        ledger.transition(job, JobState.PUBLISHED)
    result = _recording(target, key)
    return dict(
        publication_id=key,
        recording_fingerprint=result.recording_fingerprint,
        bundle_id=expected_bundle_id,
        row_count=result.row_count,
        job_id=job,
        purpose=PURPOSE,
        decision_eligibility_asserted=False,
    )


@dataclass(frozen=True)
class WindowPublication:
    publication_id: str
    recording_fingerprint: str
    bundle_id: str
    request: bundle.WindowBundleRequest
    manifest_bytes: bytes
    policy_json: str
    row_count: int
    publication_recorded_at: str
    origin_audit_success_recorded_at: str
    purpose: str = PURPOSE
    clock_semantics: str = CLOCK
    research_publication_verified: bool = True
    current_source_checked: bool = False
    decision_eligibility_asserted: bool = False
    availability_verified: bool = False
    economic_validity_verified: bool = False
    authoritative_market_coverage_verified: bool = False
    canonical_contract_id: None = None


def _recording(c: Any, key: str) -> WindowPublication:
    if not bundle.pin(key):
        raise ValueError("EXACT_WINDOW_PUBLICATION_ID_REQUIRED")
    c.execute("BEGIN TRANSACTION")
    try:
        _schema(c)
        table = name(c, "gold", DOMAIN[1])
        text = native._text
        row = c.execute(
            f"SELECT {text('scope_id', 64)},{text('window_build_id', 64)},"
            "CASE WHEN octet_length(request_bytes)<=512 THEN request_bytes END,"
            f"{text('bundle_id', 64)},manifest_byte_count,row_count,"
            "CASE WHEN octet_length(policy_bytes)<=512 THEN policy_bytes END,"
            f"{text('feature_version')},{text('purpose')},{text('clock_semantics')},"
            "event_ts,published_at,effective_from,effective_to,decision_eligibility_asserted,"
            f"{text('first_job_id')} FROM {table} WHERE build_id=?",
            [key],
        ).fetchone()
        if row is None or any(row[i] is None for i in (0, 1, 2, 3, 6, 15)):
            raise ValueError("WINDOW_PUBLICATION_MISSING_OR_COMPONENT_BOUND")
        budget = c.execute(
            f"SELECT count(*),coalesce(sum(octet_length(manifest_bytes)),0) FROM {table} "
            "WHERE build_id=? OR scope_id=? OR window_build_id=?",
            [key, row[0], row[1]],
        ).fetchone()
        if budget is None or budget[0] != 1 or not 1 <= budget[1] <= bundle.MAX_BYTES:
            raise ValueError("WINDOW_PUBLICATION_COVERAGE_OR_AGGREGATE_BYTE_BOUND")
        payload = c.execute(
            f"SELECT CASE WHEN octet_length(manifest_bytes)<=? THEN manifest_bytes END "
            f"FROM {table} WHERE build_id=?",
            [bundle.MAX_BYTES, key],
        ).fetchone()
        links = c.execute(
            f"SELECT {text('job_id')},{text('scope_id', 64)},{text('window_build_id', 64)},"
            f"{text('build_id', 64)} FROM {name(c, 'gold', DOMAIN[2])} "
            "WHERE build_id=? OR scope_id=? OR window_build_id=? OR job_id=? LIMIT 3",
            [key, row[0], row[1], row[15]],
        ).fetchall()
        jobs = c.execute(
            f"SELECT {text('job_id')},{text('parent_job_id')},{text('command_name')},"
            f"{text('actor_id')},{text('scope_ref', 71)},{text('code_revision', 40)},"
            f"{text('config_hash', 64)},created_at FROM {name(c, 'medallion_audit', 'jobs')} "
            "WHERE scope_ref=? OR job_id=? LIMIT 3",
            ["sha256:" + row[0], row[15]],
        ).fetchall()
        history = c.execute(
            f"SELECT {text('job_id')},event_index,CASE WHEN length(state)<=32 THEN state END,"
            "recorded_at,CASE WHEN octet_length(encode(reason_code))<=64 THEN reason_code END,"
            "(reason_code IS NULL OR octet_length(encode(reason_code))<=64) "
            f"FROM {name(c, 'medallion_audit', 'job_events')} "
            "WHERE job_id=? ORDER BY event_index LIMIT 7",
            [row[15]],
        ).fetchall()
        c.execute("COMMIT")
    except BaseException:
        c.execute("ROLLBACK")
        raise
    request = bundle.WindowBundleRequest(**json.loads(bytes(row[2])))
    if (
        payload is None
        or payload[0] is None
        or row[0] != scope_id(request.build_id)
        or row[1] != request.build_id
        or bytes(row[2]) != bundle.canonical(asdict(request))
        or publication_id(request.build_id, row[3]) != key
        or row[7:11] != (VERSION, PURPOSE, CLOCK, None)
        or row[12:15] != (None, None, False)
    ):
        raise ValueError("WINDOW_PUBLICATION_METADATA_OR_CLAIMS_MISMATCH")
    raw = bytes(payload[0])
    bundle.replay_window_bundle(raw, expected_bundle_id=row[3])
    doc = json.loads(raw)
    if (
        doc["request"] != asdict(request)
        or row[4] != len(raw)
        or row[5] != len(doc["outputs"])
        or bytes(row[6]) != bundle.canonical(doc["policy"])
    ):
        raise ValueError("WINDOW_PUBLICATION_COMPLETE_MEMBERSHIP_OR_POLICY_MISMATCH")
    if links != [(row[15], row[0], request.build_id, key)] or len(jobs) != 1:
        raise ValueError("WINDOW_PUBLICATION_ORIGINAL_LINK_OR_SCOPED_JOB_OBLIGATION")
    job = jobs[0]
    state, success_at = native._lifecycle(history)
    if (
        job[:3] != (row[15], None, COMMAND)
        or not native._identifier(job[3])
        or job[4] != "sha256:" + row[0]
        or type(job[5]) is not str
        or re.fullmatch(r"[a-f0-9]{40}", job[5]) is None
        or job[6] != _config(request, row[3])
        or state != "SUCCEEDED"
        or success_at is None
    ):
        raise ValueError("WINDOW_PUBLICATION_ORIGINAL_AUDIT_NOT_VERIFIED")
    native._instant(job[7])
    at = native._instant(row[11])
    metadata = [*row[:2], bytes(row[2]).hex(), *row[3:6], bytes(row[6]).hex(), *row[7:]]
    fingerprint = native._hash([VERSION, key, metadata, bundle.sha(raw), links, jobs, history])
    return WindowPublication(
        key, fingerprint, row[3], request, raw, bytes(row[6]).decode(), row[5], at, success_at
    )


def read_window_publication(
    c: Any, *, publication_id: str, expected_recording_fingerprint: str
) -> WindowPublication:
    if not bundle.pin(expected_recording_fingerprint):
        raise ValueError("EXACT_WINDOW_PUBLICATION_RECORDING_PIN_REQUIRED")
    if c.execute(
        "SELECT readonly FROM duckdb_databases() WHERE database_name=current_database()"
    ).fetchall() != [(True,)]:
        raise ValueError("READONLY_WINDOW_PUBLICATION_REQUIRED")
    result = _recording(c, publication_id)
    if result.recording_fingerprint != expected_recording_fingerprint:
        raise ValueError("WINDOW_PUBLICATION_RECORDING_FINGERPRINT_CHANGED")
    return result


def revalidate_window_publication(
    bronze: Any,
    silver: Any,
    geometry: Any,
    returns: Any,
    windows: Any,
    publications: Any,
    *,
    publication_id: str,
    expected_recording_fingerprint: str,
) -> WindowPublication:
    sources = (bronze, silver, geometry, returns, windows)
    for c in sources:
        native.foundation._separate(c, publications)
    args = dict(
        publication_id=publication_id, expected_recording_fingerprint=expected_recording_fingerprint
    )
    first = read_window_publication(publications, **args)
    bundle.revalidate_window_bundle(
        *sources, raw=first.manifest_bytes, expected_bundle_id=first.bundle_id
    )
    if read_window_publication(publications, **args) != first:
        raise ValueError("WINDOW_PUBLICATION_CHANGED_DURING_REVALIDATION")
    return first
