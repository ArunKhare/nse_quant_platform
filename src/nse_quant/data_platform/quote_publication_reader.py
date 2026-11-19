"""Read-only verification of archived research snapshots, not live/decision admission."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from nse_quant.data_platform.feature_bundle import (
    BUNDLE_VERSION,
    QuoteFeatureBundle,
    decode_quote_bundle,
    valid_pin,
)

READER_VERSION = "research-quote-publication-consumer@1"
PUBLICATION_VERSION = "research-quote-publication@1"
POLICY_VERSION = "research-only-publication-policy@1"
COMMAND = "publish.research_quote_bundle@1"
PURPOSE = "RESEARCH_ONLY"
CLOCK_SEMANTICS = "PLATFORM_RECORD_CLOCK_NOT_PROVIDER_OR_ECONOMIC_VALIDITY"
MAX_MANIFEST_BYTES = 4_194_304
MAX_ATTEMPTS = 1000
MAX_EVENTS = 6000
PHASES = ("PLANNED", "RUNNING", "STAGED", "VALIDATED", "PUBLISHED", "SUCCEEDED")


def _instant(value: object) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("AWARE_PUBLICATION_CLOCK_REQUIRED")
    return value.astimezone(UTC).isoformat()


def _canonical(value: object) -> str:
    def clock(item: object) -> str:
        if isinstance(item, datetime):
            return _instant(item)
        raise TypeError("UNSUPPORTED_PUBLICATION_EVIDENCE_VALUE")

    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=clock)


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _name(conn: Any, schema: str, table: str) -> str:
    row = conn.execute("SELECT current_database()").fetchone()
    if row is None:
        raise RuntimeError("CATALOG_UNAVAILABLE")
    return ".".join('"' + str(part).replace('"', '""') + '"' for part in (row[0], schema, table))


def _lifecycle(rows: list[tuple[Any, ...]]) -> tuple[str, str | None]:
    if not rows or len(rows) > 6:
        return "INVALID", None
    if [row[1] for row in rows] != list(range(1, len(rows) + 1)):
        return "INVALID", None
    states = tuple(row[2] for row in rows)
    try:
        clocks = [_instant(row[3]) for row in rows]
    except (ValueError, TypeError, OverflowError):
        return "INVALID", None
    for row in rows:
        reason, within_limit = row[4:6]
        if within_limit is not True or (
            reason is not None
            and (not isinstance(reason, str) or not re.fullmatch(r"[A-Z0-9_]{1,64}", reason))
        ):
            return "INVALID", None
    if states == PHASES:
        if any(row[4] is not None for row in rows):
            return "INVALID", None
        return "SUCCEEDED", clocks[-1]
    terminal = states[-1]
    prefix = states[:-1]
    if terminal in {"FAILED", "CANCELLED"} and prefix and prefix == PHASES[: len(prefix)]:
        if terminal == "CANCELLED" and prefix[-1] == "PUBLISHED":
            return "INVALID", None
        if any(row[4] is not None for row in rows[:-1]):
            return "INVALID", None
        return terminal, None
    if len(states) < len(PHASES) and states == PHASES[: len(states)]:
        return "INCOMPLETE", None
    return "INVALID", None


@dataclass(frozen=True)
class ResearchPublicationEvidence:
    reader_version: str
    publication_id: str
    status: str
    reason_code: str
    purpose: str | None = None
    bundle_id: str | None = None
    publication_recorded_at: str | None = None
    origin_audit_success_recorded_at: str | None = None
    clock_semantics: str | None = None
    successful_attempt_job_ids: tuple[str, ...] = ()
    bundle: QuoteFeatureBundle | None = None
    evidence_fingerprint: str | None = None
    research_publication_verified: bool = False
    availability_time_known: bool = False
    source_current_checked: bool = False
    historical_validity_asserted: bool = False
    decision_eligibility_asserted: bool = False


def read_research_publication(
    publications: Any,
    *,
    publication_id: str,
) -> ResearchPublicationEvidence:
    """One owned read-only file-backed connection, no outer transaction.

    Reads one registry snapshot, not live Gold/source/staging/filesystem paths.
    No as-of availability proof, repair, authorization bypass or decision admission.
    """
    if not valid_pin(publication_id):
        raise ValueError("EXACT_RESEARCH_PUBLICATION_PIN_REQUIRED")
    catalog = publications.execute("SELECT current_database()").fetchone()
    databases = publications.execute("PRAGMA database_list").fetchall()
    if catalog is None or not any(row[1] == catalog[0] and row[2] for row in databases):
        raise ValueError("FILE_BACKED_PUBLICATION_DATABASE_REQUIRED")

    def blocked(reason: str) -> ResearchPublicationEvidence:
        return ResearchPublicationEvidence(READER_VERSION, publication_id, "blocked", reason)

    records = _name(publications, "gold", "quote_bundle_publications")
    attempts = _name(publications, "gold", "quote_publication_attempts")
    versions = _name(publications, "gold", "quote_publication_schema_versions")
    audit_versions = _name(publications, "medallion_audit", "schema_versions")
    contracts = _name(publications, "medallion_audit", "dataset_contracts")
    jobs = _name(publications, "medallion_audit", "jobs")
    events = _name(publications, "medallion_audit", "job_events")
    publications.execute("BEGIN TRANSACTION")
    try:
        dedicated = (
            publications.execute(
                "SELECT 1 FROM information_schema.tables WHERE table_catalog=current_database() "
                "AND (table_schema NOT IN ('gold','medallion_audit') OR (table_schema='gold' "
                "AND table_name NOT IN ('quote_publication_schema_versions',"
                "'quote_bundle_publications',"
                "'quote_publication_attempts'))) LIMIT 1"
            ).fetchone()
            is None
        )
        schema = publications.execute(f"SELECT version FROM {versions} LIMIT 2").fetchall()
        audit = publications.execute(f"SELECT version FROM {audit_versions} LIMIT 2").fetchall()
        contract = publications.execute(
            f"SELECT fingerprint,CASE WHEN octet_length(encode(contract_json))<=32768 "
            f"THEN contract_json ELSE NULL END FROM {contracts} "
            "WHERE dataset_name='gold.quote_bundle_publications' AND contract_version='1'"
        ).fetchone()
        record = publications.execute(
            f"SELECT feature_version,policy_version,bundle_id,purpose,"
            f"CASE WHEN length(artifact_root)<=32768 THEN artifact_root ELSE NULL END,"
            f"membership_fingerprint,member_count,manifest_hash,manifest_byte_count,"
            f"CASE WHEN octet_length(manifest_bytes)<=? THEN manifest_bytes ELSE NULL END,"
            f"first_stage_evidence_fingerprint,clock_semantics,event_ts,published_at,"
            f"effective_from,"
            f"effective_to,historical_validity_asserted,decision_eligibility_asserted,first_job_id "
            f"FROM {records} WHERE build_id=?",
            [MAX_MANIFEST_BYTES, publication_id],
        ).fetchone()
        linked = publications.execute(
            f"SELECT a.job_id,a.approved_stage_fingerprint,a.verified_stage_fingerprint,"
            f"j.command_name,j.scope_ref,j.config_hash,"
            f"CASE WHEN length(j.actor_id)<=4096 THEN j.actor_id ELSE NULL END,"
            f"CASE WHEN length(j.code_revision)<=4096 "
            f"THEN j.code_revision ELSE NULL END "
            f"FROM {attempts} a LEFT JOIN {jobs} j ON j.job_id=a.job_id "
            "WHERE a.build_id=? ORDER BY a.job_id LIMIT ?",
            [publication_id, MAX_ATTEMPTS + 1],
        ).fetchall()
        lifecycle_rows = publications.execute(
            f"SELECT e.job_id,e.event_index,CASE WHEN length(e.state)<=32 "
            f"THEN e.state ELSE NULL END,"
            f"e.recorded_at,CASE WHEN octet_length(encode(e.reason_code))<=64 "
            f"THEN e.reason_code ELSE NULL END,"
            f"(e.reason_code IS NULL OR octet_length(encode(e.reason_code))<=64) "
            f"FROM {events} e JOIN {attempts} a ON a.job_id=e.job_id "
            "WHERE a.build_id=? ORDER BY e.job_id,e.event_index LIMIT ?",
            [publication_id, MAX_EVENTS + 1],
        ).fetchall()
        publications.execute("COMMIT")
    except BaseException:
        publications.execute("ROLLBACK")
        raise
    if not dedicated:
        return blocked("DEDICATED_PUBLICATION_REGISTRY_NOT_VERIFIED")
    if schema != [(1,)] or audit != [(1,)]:
        return blocked("UNSUPPORTED_PUBLICATION_REGISTRY_SCHEMA")
    if record is None:
        return blocked("RESEARCH_PUBLICATION_NOT_FOUND")
    expected_contract = {
        "name": "gold.quote_bundle_publications",
        "version": "1",
        "layer": "gold",
        "write_policy": "versioned_builds",
        "entity_keys": ["build_id"],
        "required_columns": ["build_id", "event_ts", "published_at", "feature_version"],
        "owner": "native_research_quote_publication",
    }
    if contract != (_hash(expected_contract), _canonical(expected_contract)):
        return blocked("PUBLICATION_CONTRACT_NOT_VERIFIED")
    if record[:2] != (PUBLICATION_VERSION, POLICY_VERSION) or record[3] != PURPOSE:
        return blocked("UNSUPPORTED_PUBLICATION_VERSION_OR_PURPOSE")
    expected_identity = _hash([[PUBLICATION_VERSION, POLICY_VERSION], record[2], PURPOSE])
    if not valid_pin(record[2]) or expected_identity != publication_id:
        return blocked("PUBLICATION_IDENTITY_MISMATCH")
    if (
        not isinstance(record[4], str)
        or not record[4].strip()
        or not valid_pin(record[5])
        or record[7] != record[2]
        or type(record[6]) is not int
        or not 1 <= record[6] <= 64
        or type(record[8]) is not int
        or not 1 <= record[8] <= MAX_MANIFEST_BYTES
        or not valid_pin(record[10])
        or record[11] != CLOCK_SEMANTICS
        or record[12] is not None
        or record[14] is not None
        or record[15] is not None
        or record[16] is not False
        or record[17] is not False
    ):
        return blocked("PUBLICATION_METADATA_OR_CLAIMS_MISMATCH")
    try:
        record_clock = _instant(record[13])
    except (ValueError, TypeError, OverflowError):
        return blocked("INVALID_PUBLICATION_RECORD_CLOCK")
    if BUNDLE_VERSION != "quote-feature-bundle@1":
        return blocked("UNSUPPORTED_ARCHIVE_BUNDLE_CODEC")
    if record[9] is None:
        return blocked("PUBLICATION_MANIFEST_LIMIT")
    raw = bytes(record[9])
    if len(raw) != record[8]:
        return blocked("PUBLICATION_MANIFEST_LENGTH_MISMATCH")
    try:
        bundle = decode_quote_bundle(raw, expected_bundle_id=record[2])
    except (ValueError, TypeError, RecursionError):
        return blocked("PUBLICATION_MANIFEST_NOT_VERIFIED")
    if bundle.membership_fingerprint != record[5] or len(bundle.members) != record[6]:
        return blocked("PUBLICATION_MEMBERSHIP_MISMATCH")
    if len(linked) > MAX_ATTEMPTS or len(lifecycle_rows) > MAX_EVENTS:
        return blocked("PUBLICATION_AUDIT_BOUND_REVIEW_REQUIRED")
    if not linked or record[18] not in {attempt[0] for attempt in linked}:
        return blocked("PUBLICATION_ORIGIN_LINK_MISSING")
    grouped: dict[str, list[tuple[Any, ...]]] = {}
    for event in lifecycle_rows:
        grouped.setdefault(event[0], []).append(event)
    expected_config = _hash([[PUBLICATION_VERSION, POLICY_VERSION], PURPOSE, record[4]])
    succeeded: list[str] = []
    origin_success = None
    for job, approved, verified, command, scope, config, actor, revision in linked:
        if (
            not isinstance(job, str)
            or not job.strip()
            or not valid_pin(approved)
            or approved != verified
            or (command, scope, config) != (COMMAND, "sha256:" + publication_id, expected_config)
            or not isinstance(actor, str)
            or not actor.strip()
            or not isinstance(revision, str)
            or not revision.strip()
        ):
            return blocked("PUBLICATION_ATTEMPT_IDENTITY_MISMATCH")
        state, success_clock = _lifecycle(grouped.get(job, []))
        if state == "INVALID":
            return blocked("PUBLICATION_LIFECYCLE_NOT_VERIFIED")
        if state == "INCOMPLETE":
            return blocked("PUBLICATION_ATTEMPT_NOT_TERMINAL")
        if state == "SUCCEEDED":
            succeeded.append(job)
        if job == record[18]:
            if approved != record[10] or state != "SUCCEEDED":
                return blocked("PUBLICATION_ORIGIN_NOT_SUCCESSFUL")
            origin_success = success_clock
    if origin_success is None:
        return blocked("PUBLICATION_ORIGIN_NOT_SUCCESSFUL")
    fingerprint_record = record[:9] + (hashlib.sha256(raw).hexdigest(),) + record[10:]
    fingerprint = _hash(
        [
            READER_VERSION,
            publication_id,
            fingerprint_record,
            linked,
            lifecycle_rows,
        ]
    )
    return ResearchPublicationEvidence(
        READER_VERSION,
        publication_id,
        "verified_research_snapshot",
        "ARCHIVED_CONTENT_AND_PUBLICATION_AUDITS_VERIFIED",
        PURPOSE,
        record[2],
        record_clock,
        origin_success,
        CLOCK_SEMANTICS,
        tuple(succeeded),
        bundle,
        fingerprint,
        True,
    )
