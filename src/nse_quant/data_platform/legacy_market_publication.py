"""Audited research publication extension for complete migrated-price bundles.

Uses native audit, contracts and publication lifecycle verification. Quote @1 is unchanged.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from nse_quant.data_platform import legacy_market_gold_bundle as bundle
from nse_quant.data_platform import legacy_market_silver_store as foundation
from nse_quant.data_platform.audit import AuditLedger, JobState
from nse_quant.data_platform.contracts import DatasetContract, Layer, WritePolicy
from nse_quant.data_platform.quote_publication_reader import _canonical, _instant, _lifecycle

VERSION = "legacy-price-research-publication@1"
POLICY = "legacy-price-research-only-policy@1"
COMMAND = "publish.legacy_price_research_bundle@1"
PURPOSE = "RESEARCH_ONLY"
CLOCK = "PLATFORM_RECORD_CLOCK_NOT_PROVIDER_OR_ECONOMIC_VALIDITY"
DOMAIN = ("legacy_publication_versions", "legacy_publications", "legacy_publication_attempts")
TABLES = {("gold", n) for n in DOMAIN} | {
    ("medallion_audit", n) for n in ("schema_versions", "dataset_contracts", "jobs", "job_events")
}
CONTRACT = DatasetContract(
    "gold.legacy_publications",
    "1",
    Layer.GOLD,
    WritePolicy.VERSIONED_BUILDS,
    ("build_id",),
    ("build_id", "event_ts", "published_at", "feature_version"),
    "native_legacy_research_publication",
)
name = foundation.name


def _hash(value: object) -> str:
    return bundle.gold.sha(_canonical(value).encode())


def _definition() -> bytes:
    return bundle.gold.canonical(
        [
            VERSION,
            POLICY,
            bundle.VERSION,
            CONTRACT.canonical_json(),
            bundle.MAX_BYTES,
            "one complete pinned Gold build; first-write scope excludes recording and bundle pins",
            "retained replay is not current-source verification; "
            "research-only never decision input",
            CLOCK,
        ]
    )


def scope_id(gold_build_id: str) -> str:
    if not bundle.gold.pin(gold_build_id):
        raise ValueError("EXACT_PUBLICATION_GOLD_BUILD_REQUIRED")
    return _hash([VERSION, gold_build_id])


def publication_id(gold_build_id: str, bundle_id: str) -> str:
    if not bundle.gold.pin(bundle_id):
        raise ValueError("EXACT_PUBLICATION_BUNDLE_REQUIRED")
    return _hash([VERSION, POLICY, scope_id(gold_build_id), bundle_id, PURPOSE])


def _identifier(value: object) -> bool:
    return (
        type(value) is str
        and 1 <= len(value.encode()) <= 128
        and value == value.strip()
        and all(ord(c) >= 32 for c in value)
    )


def _owned(conn: Any, *, complete: bool) -> None:
    paths = conn.execute(
        "SELECT path FROM duckdb_databases() WHERE database_name=current_database()"
    ).fetchall()
    if len(paths) != 1 or not paths[0][0]:
        raise ValueError("FILE_BACKED_PUBLICATION_REQUIRED")
    rows = conn.execute(
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
        raise ValueError("DEDICATED_LEGACY_PUBLICATION_REQUIRED")


def initialize_legacy_publication(conn: Any) -> None:
    """Explicit empty dedicated file only; partial initialization cannot be adopted."""
    _owned(conn, complete=False)
    if conn.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_catalog=current_database() LIMIT 1"
    ).fetchone():
        raise ValueError("EMPTY_PUBLICATION_INITIALIZATION_REQUIRED")
    AuditLedger(conn).initialize()
    versions, records, attempts = (name(conn, "gold", n) for n in DOMAIN)
    conn.execute("BEGIN TRANSACTION")
    try:
        conn.execute(f"CREATE SCHEMA {versions.rsplit('.', 1)[0]}")
        conn.execute(f"CREATE TABLE {versions} (version INTEGER PRIMARY KEY,definition BLOB)")
        conn.execute(f"INSERT INTO {versions} VALUES (1,?)", [_definition()])
        conn.execute(f"""CREATE TABLE {records} (
            build_id VARCHAR PRIMARY KEY,scope_id VARCHAR UNIQUE NOT NULL,
            gold_build_id VARCHAR UNIQUE NOT NULL,request_bytes BLOB NOT NULL,
            bundle_id VARCHAR NOT NULL,manifest_bytes BLOB NOT NULL,
            manifest_byte_count BIGINT NOT NULL,row_count INTEGER NOT NULL,
            feature_version VARCHAR NOT NULL,purpose VARCHAR NOT NULL,
            clock_semantics VARCHAR NOT NULL,event_ts TIMESTAMPTZ,
            published_at TIMESTAMPTZ NOT NULL,effective_from TIMESTAMPTZ,
            effective_to TIMESTAMPTZ,decision_eligibility_asserted BOOLEAN NOT NULL,
            first_job_id VARCHAR NOT NULL)""")
        conn.execute(f"""CREATE TABLE {attempts} (
            job_id VARCHAR PRIMARY KEY,scope_id VARCHAR NOT NULL,
            gold_build_id VARCHAR NOT NULL,build_id VARCHAR NOT NULL)""")
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    AuditLedger(conn).register_contract(CONTRACT)


def _text(column: str, bound: int = 128) -> str:
    # Only internal constant identifiers are passed to this helper.
    return f"CASE WHEN octet_length(encode({column}))<={bound} THEN {column} END"


def _schema(conn: Any) -> None:
    _owned(conn, complete=True)
    versions = name(conn, "gold", DOMAIN[0])
    contracts = name(conn, "medallion_audit", "dataset_contracts")
    audit = name(conn, "medallion_audit", "schema_versions")
    if conn.execute(
        f"SELECT version,CASE WHEN octet_length(definition)<=32768 THEN definition END "
        f"FROM {versions} LIMIT 2"
    ).fetchall() != [(1, _definition())]:
        raise ValueError("PUBLICATION_DEFINITION_DRIFT")
    if conn.execute(
        f"SELECT fingerprint,CASE WHEN octet_length(encode(contract_json))<=32768 "
        f"THEN contract_json END FROM {contracts} WHERE dataset_name=? AND contract_version='1'",
        [CONTRACT.name],
    ).fetchall() != [(CONTRACT.fingerprint, CONTRACT.canonical_json())]:
        raise ValueError("PUBLICATION_CONTRACT_DRIFT")
    if conn.execute(f"SELECT version FROM {audit} LIMIT 2").fetchall() != [(1,)]:
        raise ValueError("PUBLICATION_AUDIT_SCHEMA_DRIFT")


def _config(request: bundle.LegacyGoldBundleRequest, reviewed_bundle_id: str) -> str:
    return _hash([_definition().hex(), asdict(request), reviewed_bundle_id])


def _unused(conn: Any, request: bundle.LegacyGoldBundleRequest) -> None:
    scope = scope_id(request.build_id)
    for table in DOMAIN[1:]:
        if conn.execute(
            f"SELECT 1 FROM {name(conn, 'gold', table)} "
            "WHERE scope_id=? OR gold_build_id=? LIMIT 1",
            [scope, request.build_id],
        ).fetchone():
            raise ValueError("PUBLICATION_FIRST_WRITE_OR_ORPHAN_OBLIGATION")
    if conn.execute(
        f"SELECT 1 FROM {name(conn, 'medallion_audit', 'jobs')} WHERE scope_ref=? LIMIT 1",
        ["sha256:" + scope],
    ).fetchone():
        raise ValueError("PUBLICATION_FIRST_WRITE_ORIGINAL_AUDIT_OBLIGATION")


def publish_legacy_research_bundle(
    bronze: Any,
    silver: Any,
    gold: Any,
    target: Any,
    *,
    request: bundle.LegacyGoldBundleRequest,
    expected_bundle_id: str,
    actor_id: str,
    code_revision: str,
    purpose: str,
    allow_research_publication: bool = False,
) -> dict[str, Any]:
    """Explicit intent gate, not authorization. Only disposable synthetic use is released.

    Separate initialized target/read-only sources; no outer transaction or audit healing.
    Domain commit precedes separate PUBLISHED/SUCCEEDED audit transitions.
    """
    if allow_research_publication is not True or purpose != PURPOSE:
        raise ValueError("EXPLICIT_RESEARCH_PUBLICATION_REQUIRED")
    if type(request) is not bundle.LegacyGoldBundleRequest:
        raise TypeError("TYPED_PUBLICATION_REQUEST_REQUIRED")
    request = bundle.LegacyGoldBundleRequest(**asdict(request))
    if (
        not bundle.gold.pin(expected_bundle_id)
        or not _identifier(actor_id)
        or type(code_revision) is not str
        or re.fullmatch(r"[a-f0-9]{40}", code_revision) is None
    ):
        raise ValueError("EXACT_PUBLICATION_EXECUTION_AND_REVIEW_PINS_REQUIRED")
    for source in (bronze, silver, gold):
        foundation._separate(source, target)
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
        first = bundle.assemble_legacy_gold_bundle(bronze, silver, gold, request=request)
        if bundle.gold.sha(first) != expected_bundle_id:
            raise ValueError("REVIEWED_PUBLICATION_BUNDLE_CHANGED")
        ledger.transition(job, JobState.STAGED)
        second = bundle.assemble_legacy_gold_bundle(bronze, silver, gold, request=request)
        if second != first:
            raise ValueError("PUBLICATION_COMPLETE_NATIVE_SOURCE_DRIFT")
        bundle.replay_legacy_gold_bundle(first, expected_bundle_id=expected_bundle_id)
        ledger.transition(job, JobState.VALIDATED)
        at = datetime.now(UTC)
        count = len(json.loads(first)["outputs"])
        target.execute("BEGIN TRANSACTION")
        try:
            target.execute(
                f"INSERT INTO {name(target, 'gold', DOMAIN[1])} VALUES "
                "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [
                    key,
                    scope,
                    request.build_id,
                    bundle.gold.canonical(asdict(request)),
                    expected_bundle_id,
                    first,
                    len(first),
                    count,
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
    evidence = _recording(target, key)
    return dict(
        publication_id=key,
        recording_fingerprint=evidence.recording_fingerprint,
        bundle_id=expected_bundle_id,
        row_count=count,
        job_id=job,
        purpose=PURPOSE,
        decision_eligibility_asserted=False,
    )


@dataclass(frozen=True)
class LegacyResearchPublication:
    publication_id: str
    recording_fingerprint: str
    bundle_id: str
    request: bundle.LegacyGoldBundleRequest
    manifest_bytes: bytes
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
    canonical_contract_id: None = None


def _recording(conn: Any, key: str) -> LegacyResearchPublication:
    if not bundle.gold.pin(key):
        raise ValueError("EXACT_PUBLICATION_ID_REQUIRED")
    conn.execute("BEGIN TRANSACTION")
    try:
        _schema(conn)
        records = name(conn, "gold", DOMAIN[1])
        row = conn.execute(
            f"SELECT {_text('scope_id', 64)},{_text('gold_build_id', 64)},"
            "CASE WHEN octet_length(request_bytes)<=512 "
            f"THEN request_bytes END,{_text('bundle_id', 64)},manifest_byte_count,row_count,"
            f"{_text('feature_version')},{_text('purpose')},{_text('clock_semantics')},"
            "event_ts,published_at,effective_from,effective_to,decision_eligibility_asserted,"
            f"{_text('first_job_id')} FROM {records} WHERE build_id=?",
            [key],
        ).fetchone()
        if row is None or row[2] is None:
            raise ValueError("PUBLICATION_RECORD_MISSING_OR_REQUEST_BOUND")
        budget = conn.execute(
            f"SELECT count(*),coalesce(sum(octet_length(manifest_bytes)),0) FROM {records} "
            "WHERE build_id=? OR scope_id=? OR gold_build_id=?",
            [key, row[0], row[1]],
        ).fetchone()
        if budget is None or budget[0] != 1 or not 1 <= budget[1] <= bundle.MAX_BYTES:
            raise ValueError("PUBLICATION_COVERAGE_OR_AGGREGATE_BYTE_BOUND")
        payload = conn.execute(
            f"SELECT CASE WHEN octet_length(manifest_bytes)<=? THEN manifest_bytes END "
            f"FROM {records} WHERE build_id=?",
            [bundle.MAX_BYTES, key],
        ).fetchone()
        attempts = conn.execute(
            f"SELECT {_text('job_id')},{_text('scope_id', 64)},"
            f"{_text('gold_build_id', 64)},{_text('build_id', 64)} "
            f"FROM {name(conn, 'gold', DOMAIN[2])} "
            "WHERE build_id=? OR scope_id=? OR gold_build_id=? OR job_id=? LIMIT 3",
            [key, row[0], row[1], row[14]],
        ).fetchall()
        jobs = conn.execute(
            f"SELECT {_text('job_id')},{_text('parent_job_id')},{_text('command_name')},"
            f"{_text('actor_id')},{_text('scope_ref', 71)},"
            "CASE WHEN octet_length(encode(code_revision))<=40 THEN code_revision END,"
            f"{_text('config_hash', 64)},created_at "
            f"FROM {name(conn, 'medallion_audit', 'jobs')} "
            "WHERE scope_ref=? OR job_id=? LIMIT 3",
            ["sha256:" + row[0], row[14]],
        ).fetchall()
        history = conn.execute(
            f"SELECT {_text('job_id')},event_index,CASE WHEN length(state)<=32 "
            "THEN state END,recorded_at,"
            "CASE WHEN octet_length(encode(reason_code))<=64 THEN reason_code END,"
            "(reason_code IS NULL OR octet_length(encode(reason_code))<=64) "
            f"FROM {name(conn, 'medallion_audit', 'job_events')} "
            "WHERE job_id=? ORDER BY event_index LIMIT 7",
            [row[14]],
        ).fetchall()
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    try:
        request = bundle.LegacyGoldBundleRequest(**json.loads(bytes(row[2])))
    except (TypeError, ValueError, KeyError, RecursionError):
        raise ValueError("PUBLICATION_REQUEST_MALFORMED") from None
    if (
        payload is None
        or payload[0] is None
        or row[0] != scope_id(request.build_id)
        or row[1] != request.build_id
        or bytes(row[2]) != bundle.gold.canonical(asdict(request))
        or publication_id(request.build_id, row[3]) != key
        or row[6:10] != (VERSION, PURPOSE, CLOCK, None)
        or row[11:14] != (None, None, False)
    ):
        raise ValueError("PUBLICATION_METADATA_OR_CLAIMS_MISMATCH")
    raw = bytes(payload[0])
    bundle.replay_legacy_gold_bundle(raw, expected_bundle_id=row[3])
    content = json.loads(raw)
    if (
        content["request"] != asdict(request)
        or row[4] != len(raw)
        or row[5] != len(content["outputs"])
    ):
        raise ValueError("PUBLICATION_COMPLETE_MEMBERSHIP_MISMATCH")
    if attempts != [(row[14], row[0], request.build_id, key)] or len(jobs) != 1:
        raise ValueError("PUBLICATION_ORIGINAL_LINK_OR_SCOPED_JOB_OBLIGATION")
    job = jobs[0]
    state, success_at = _lifecycle(history)
    if (
        job[:3] != (row[14], None, COMMAND)
        or not _identifier(job[3])
        or job[4] != "sha256:" + row[0]
        or type(job[5]) is not str
        or re.fullmatch(r"[a-f0-9]{40}", job[5]) is None
        or job[6] != _config(request, row[3])
        or state != "SUCCEEDED"
        or success_at is None
    ):
        raise ValueError("PUBLICATION_ORIGINAL_AUDIT_NOT_VERIFIED")
    _instant(job[7])
    recorded_at = _instant(row[10])
    metadata = [*row[:2], bytes(row[2]).hex(), *row[3:]]
    fingerprint = _hash([VERSION, key, metadata, bundle.gold.sha(raw), attempts, jobs, history])
    return LegacyResearchPublication(
        key, fingerprint, row[3], request, raw, row[5], recorded_at, success_at
    )


def read_legacy_research_publication(
    conn: Any,
    *,
    publication_id: str,
    expected_recording_fingerprint: str,
) -> LegacyResearchPublication:
    """Pinned retained registry snapshot; does not consult current Gold or upstream."""
    if not bundle.gold.pin(expected_recording_fingerprint):
        raise ValueError("EXACT_PUBLICATION_RECORDING_PIN_REQUIRED")
    if conn.execute(
        "SELECT readonly FROM duckdb_databases() WHERE database_name=current_database()"
    ).fetchall() != [(True,)]:
        raise ValueError("READONLY_PUBLICATION_REQUIRED")
    result = _recording(conn, publication_id)
    if result.recording_fingerprint != expected_recording_fingerprint:
        raise ValueError("PUBLICATION_RECORDING_FINGERPRINT_CHANGED")
    return result


def revalidate_legacy_research_publication(
    bronze: Any,
    silver: Any,
    gold: Any,
    publications: Any,
    *,
    publication_id: str,
    expected_recording_fingerprint: str,
) -> LegacyResearchPublication:
    """Retained registry plus actual current native upstream, NOT current legacy SQL."""
    for source in (bronze, silver, gold):
        foundation._separate(source, publications)
    args = dict(
        publication_id=publication_id, expected_recording_fingerprint=expected_recording_fingerprint
    )
    first = read_legacy_research_publication(publications, **args)
    bundle.revalidate_legacy_gold_bundle(
        bronze,
        silver,
        gold,
        raw=first.manifest_bytes,
        expected_bundle_id=first.bundle_id,
    )
    second = read_legacy_research_publication(publications, **args)
    if first != second:
        raise ValueError("PUBLICATION_CHANGED_DURING_REVALIDATION")
    return first
