"""Explicit research-only publication records. No decision admission or audit repair."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nse_quant.data_platform.audit import AuditLedger, JobState
from nse_quant.data_platform.contracts import DatasetContract, Layer, WritePolicy
from nse_quant.data_platform.feature_bundle import MAX_BUNDLE_BYTES, encode_quote_bundle, valid_pin
from nse_quant.data_platform.quote_bundle_stage_reader import read_staged_quote_bundle

PUBLICATION_VERSION = "research-quote-publication@1"
POLICY_VERSION = "research-only-publication-policy@1"
COMMAND = "publish.research_quote_bundle@1"
PURPOSE = "RESEARCH_ONLY"
CLOCK_SEMANTICS = "PLATFORM_RECORD_CLOCK_NOT_PROVIDER_OR_ECONOMIC_VALIDITY"
MAX_ATTEMPTS = 1000


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _name(conn: Any, table: str, schema: str = "gold") -> str:
    row = conn.execute("SELECT current_database()").fetchone()
    if row is None:
        raise RuntimeError("CATALOG_UNAVAILABLE")
    return ".".join('"' + str(part).replace('"', '""') + '"' for part in (row[0], schema, table))


def _paths(conn: Any) -> set[Path]:
    return {
        Path(row[2]).resolve() for row in conn.execute("PRAGMA database_list").fetchall() if row[2]
    }


def publish_research_quote_bundle(
    bronze: Any,
    frame_silver: Any,
    reference_silver: Any,
    assessments: Any,
    gold: Any,
    staging: Any,
    publications: Any,
    *,
    bundle_id: str,
    artifact_root: Path,
    expected_stage_evidence_fingerprint: str,
    purpose: str,
    actor_id: str,
    code_revision: str,
    allow_publication: bool = False,
    initialize: bool = False,
) -> dict[str, object]:
    """Inputs read-only, output file-backed/single-owner, no outer transactions.

    Explicit acknowledgement and reviewed fingerprint are intent gates, NOT ACLs
    or digital signatures. Raw publication rows are not authority without completed
    attempt audits; incomplete existing publications require separate review.
    """
    if (
        PUBLICATION_VERSION != "research-quote-publication@1"
        or POLICY_VERSION != "research-only-publication-policy@1"
        or PURPOSE != "RESEARCH_ONLY"
    ):
        raise ValueError("UNSUPPORTED_RESEARCH_PUBLICATION_POLICY")
    if allow_publication is not True or purpose != PURPOSE:
        raise ValueError("EXPLICIT_RESEARCH_ONLY_PUBLICATION_REQUIRED")
    if not valid_pin(bundle_id) or not valid_pin(expected_stage_evidence_fingerprint):
        raise ValueError("EXACT_BUNDLE_AND_STAGE_EVIDENCE_PINS_REQUIRED")
    if not actor_id.strip() or not code_revision.strip():
        raise ValueError("EXECUTION_IDENTITIES_REQUIRED")
    root = artifact_root.resolve()
    sources = (bronze, frame_silver, reference_silver, assessments, gold, staging)
    catalog = publications.execute("SELECT current_database()").fetchone()
    databases = publications.execute("PRAGMA database_list").fetchall()
    if catalog is None or not any(row[1] == catalog[0] and row[2] for row in databases):
        raise ValueError("FILE_BACKED_PUBLICATION_DATABASE_REQUIRED")
    output_paths = _paths(publications)
    all_paths = set(output_paths)
    for source in sources:
        paths = _paths(source)
        if source is publications or any(
            a == b or (a.exists() and b.exists() and a.samefile(b))
            for a in output_paths
            for b in paths
        ):
            raise ValueError("SEPARATE_PUBLICATION_DATABASE_REQUIRED")
        all_paths.update(paths)
    if any(path == root or root in path.parents or path in root.parents for path in all_paths):
        raise ValueError("ARTIFACT_ROOT_MUST_BE_SEPARATE_FROM_DATABASES")
    if publications.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_catalog=current_database() "
        "AND (table_schema NOT IN ('gold','medallion_audit') OR (table_schema='gold' "
        "AND table_name NOT IN ('quote_publication_schema_versions','quote_bundle_publications',"
        "'quote_publication_attempts'))) LIMIT 1"
    ).fetchone():
        raise ValueError("DEDICATED_PUBLICATION_DATABASE_REQUIRED")
    versions = [PUBLICATION_VERSION, POLICY_VERSION]
    publication_id = _hash([versions, bundle_id, purpose])
    config = _hash([versions, purpose, str(root)])
    ledger = AuditLedger(publications)
    if initialize:
        ledger.initialize()
    job = ledger.plan_job(
        command_name=COMMAND,
        actor_id=actor_id,
        scope_ref="sha256:" + publication_id,
        code_revision=code_revision,
        config_hash=config,
    )
    schema = _name(publications, "quote_publication_schema_versions")
    records = _name(publications, "quote_bundle_publications")
    attempts = _name(publications, "quote_publication_attempts")

    def verify_stage() -> tuple[bytes, str, int]:
        evidence = read_staged_quote_bundle(*sources, bundle_id=bundle_id, artifact_root=root)
        if (
            evidence.reader_version != "staged-quote-bundle-consumer@1"
            or evidence.bundle_id != bundle_id
            or evidence.status != "verified_current"
            or evidence.reason_code != "STAGE_AND_SOURCES_RECOMPUTED"
            or evidence.active_bundle_ids != (bundle_id,)
            or not evidence.successful_attempt_job_ids
            or evidence.evidence_fingerprint != expected_stage_evidence_fingerprint
            or evidence.publication_asserted is not False
            or evidence.historical_validity_asserted is not False
            or evidence.decision_eligibility_asserted is not False
            or evidence.bundle is None
            or evidence.bundle.bundle_id != bundle_id
        ):
            raise ValueError("REVIEWED_STAGE_EVIDENCE_NOT_CURRENT")
        raw = encode_quote_bundle(evidence.bundle)
        return raw, evidence.bundle.membership_fingerprint, len(evidence.bundle.members)

    with ledger.execution(job):
        if initialize:
            publications.execute("BEGIN TRANSACTION")
            try:
                publications.execute(f"CREATE SCHEMA IF NOT EXISTS {records.rsplit('.', 1)[0]}")
                publications.execute(
                    f"CREATE TABLE IF NOT EXISTS {schema} (version INTEGER PRIMARY KEY)"
                )
                previous_versions = publications.execute(f"SELECT version FROM {schema}").fetchall()
                if previous_versions and previous_versions != [(1,)]:
                    raise ValueError("UNSUPPORTED_PUBLICATION_SCHEMA")
                if not previous_versions:
                    publications.execute(f"INSERT INTO {schema} VALUES (1)")
                publications.execute(f"""CREATE TABLE IF NOT EXISTS {records} (
                    build_id VARCHAR PRIMARY KEY,feature_version VARCHAR NOT NULL,
                    policy_version VARCHAR NOT NULL,bundle_id VARCHAR NOT NULL,
                    purpose VARCHAR NOT NULL,
                    artifact_root VARCHAR NOT NULL,membership_fingerprint VARCHAR NOT NULL,
                    member_count INTEGER NOT NULL,manifest_hash VARCHAR NOT NULL,
                    manifest_byte_count BIGINT NOT NULL,manifest_bytes BLOB NOT NULL,
                    first_stage_evidence_fingerprint VARCHAR NOT NULL,
                    clock_semantics VARCHAR NOT NULL,event_ts TIMESTAMPTZ,
                    published_at TIMESTAMPTZ NOT NULL,
                    effective_from TIMESTAMPTZ,effective_to TIMESTAMPTZ,
                    historical_validity_asserted BOOLEAN NOT NULL,
                    decision_eligibility_asserted BOOLEAN NOT NULL,
                    first_job_id VARCHAR NOT NULL)""")
                publications.execute(f"""CREATE TABLE IF NOT EXISTS {attempts} (
                    job_id VARCHAR PRIMARY KEY,build_id VARCHAR NOT NULL,
                    approved_stage_fingerprint VARCHAR NOT NULL,
                    verified_stage_fingerprint VARCHAR NOT NULL,
                    recorded_at TIMESTAMPTZ NOT NULL)""")
                publications.execute("COMMIT")
            except BaseException:
                publications.execute("ROLLBACK")
                raise
        if publications.execute(f"SELECT version FROM {schema} LIMIT 2").fetchall() != [(1,)]:
            raise ValueError("UNSUPPORTED_PUBLICATION_SCHEMA")
        ledger.register_contract(
            DatasetContract(
                name="gold.quote_bundle_publications",
                version="1",
                layer=Layer.GOLD,
                write_policy=WritePolicy.VERSIONED_BUILDS,
                entity_keys=("build_id",),
                required_columns=("build_id", "event_ts", "published_at", "feature_version"),
                owner="native_research_quote_publication",
            )
        )
        raw, membership, member_count = verify_stage()
        previous = publications.execute(
            f"SELECT feature_version,policy_version,bundle_id,purpose,artifact_root,"
            f"membership_fingerprint,member_count,manifest_hash,manifest_byte_count,"
            f"CASE WHEN octet_length(manifest_bytes)<=? THEN manifest_bytes ELSE NULL END,"
            f"first_stage_evidence_fingerprint,clock_semantics,event_ts,published_at,"
            f"effective_from,effective_to,historical_validity_asserted,"
            f"decision_eligibility_asserted,first_job_id FROM {records} WHERE build_id=?",
            [MAX_BUNDLE_BYTES, publication_id],
        ).fetchone()
        deterministic = (
            PUBLICATION_VERSION,
            POLICY_VERSION,
            bundle_id,
            purpose,
            str(root),
            membership,
            member_count,
            bundle_id,
            len(raw),
            raw,
        )
        published_at = None
        if previous is not None:
            if (
                previous[:10] != deterministic
                or not valid_pin(previous[10])
                or previous[11] != CLOCK_SEMANTICS
                or previous[12] is not None
                or not isinstance(previous[13], datetime)
                or previous[13].tzinfo is None
                or previous[13].utcoffset() is None
                or previous[14:18] != (None, None, False, False)
            ):
                raise ValueError("PUBLICATION_CONTENT_MISMATCH")
            audit_jobs = _name(publications, "jobs", "medallion_audit")
            audit_events = _name(publications, "job_events", "medallion_audit")
            linked = publications.execute(
                f"SELECT a.job_id,a.approved_stage_fingerprint,a.verified_stage_fingerprint,"
                f"j.command_name,j.scope_ref,j.config_hash,"
                f"(SELECT e.state FROM {audit_events} e WHERE e.job_id=a.job_id "
                f"ORDER BY e.event_index DESC LIMIT 1),j.actor_id,j.code_revision "
                f"FROM {attempts} a "
                f"LEFT JOIN {audit_jobs} j ON j.job_id=a.job_id "
                "WHERE a.build_id=? ORDER BY a.job_id LIMIT ?",
                [publication_id, MAX_ATTEMPTS + 1],
            ).fetchall()
            if not linked or len(linked) > MAX_ATTEMPTS:
                raise ValueError("PUBLICATION_ATTEMPT_REVIEW_REQUIRED")
            first = [row for row in linked if row[0] == previous[18]]
            if len(first) != 1 or first[0][1:3] != (previous[10], previous[10]):
                raise ValueError("PUBLICATION_ORIGIN_REVIEW_REQUIRED")
            success = False
            for audit_row in linked:
                (linked_job, approved, verified, command, scope, cfg, state, actor, revision) = (
                    audit_row
                )
                if (
                    not isinstance(linked_job, str)
                    or not linked_job.strip()
                    or not isinstance(actor, str)
                    or not actor.strip()
                    or not isinstance(revision, str)
                    or not revision.strip()
                    or not valid_pin(approved)
                    or approved != verified
                    or (command, scope, cfg) != (COMMAND, "sha256:" + publication_id, config)
                    or state not in {"SUCCEEDED", "FAILED", "CANCELLED"}
                ):
                    raise ValueError("PUBLICATION_AUDIT_REVIEW_REQUIRED")
                success = success or state == "SUCCEEDED"
            if not success:
                raise ValueError("PUBLICATION_AUDIT_REVIEW_REQUIRED")
            published_at = previous[13].astimezone(UTC)
        ledger.transition(job, JobState.STAGED)
        ledger.transition(job, JobState.VALIDATED)
        if verify_stage() != (raw, membership, member_count):
            raise ValueError("STAGE_CHANGED_DURING_PUBLICATION")
        publications.execute("BEGIN TRANSACTION")
        try:
            if previous is None:
                published_at = datetime.now(UTC)
                publications.execute(
                    f"INSERT INTO {records} VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [
                        publication_id,
                        *deterministic[:9],
                        raw,
                        expected_stage_evidence_fingerprint,
                        CLOCK_SEMANTICS,
                        None,
                        published_at,
                        None,
                        None,
                        False,
                        False,
                        job,
                    ],
                )
            publications.execute(
                f"INSERT INTO {attempts} VALUES (?,?,?,?,?)",
                [
                    job,
                    publication_id,
                    expected_stage_evidence_fingerprint,
                    expected_stage_evidence_fingerprint,
                    datetime.now(UTC),
                ],
            )
            publications.execute("COMMIT")
        except BaseException:
            publications.execute("ROLLBACK")
            raise
        ledger.transition(job, JobState.PUBLISHED)
    if published_at is None:
        raise RuntimeError("PUBLICATION_CLOCK_NOT_RECORDED")
    return {
        "publication_id": publication_id,
        "bundle_id": bundle_id,
        "job_id": job,
        "inserted": previous is None,
        "status": "PUBLISHED_RESEARCH_ONLY",
        "purpose": purpose,
        "published_at": published_at.isoformat(),
        "clock_semantics": CLOCK_SEMANTICS,
        "historical_validity_asserted": False,
        "decision_eligibility_asserted": False,
    }
