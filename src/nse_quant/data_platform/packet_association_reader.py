"""Invalidation-first read-only consumer of one persisted assessment pin."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from nse_quant.data_platform.packet_association_silver import COMMAND, STORE_VERSION
from nse_quant.data_platform.packet_reference_association import (
    ASSOCIATION_VERSION,
    PacketReferenceAssociation,
    associate_packet_reference,
)
from nse_quant.data_platform.reference_supersession import (
    MAX_ASSESSMENTS,
    AssessmentNode,
    resolve_supersession,
    valid_hash,
)

READER_VERSION = "persisted-packet-association-consumer@1"
MAX_RESULT_BYTES = 1_048_576
MAX_ATTEMPTS = 1000


def _canonical(value: object) -> str:
    def instant(item: object) -> str:
        if not isinstance(item, datetime) or item.tzinfo is None or item.utcoffset() is None:
            raise ValueError("AWARE_TIME_REQUIRED")
        return item.astimezone(UTC).isoformat()

    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=instant
    )


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _json(raw: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("DUPLICATE_JSON_KEY")
            result[key] = value
        return result

    def invalid(_value: str) -> Any:
        raise ValueError("NONFINITE_JSON")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def _name(conn: Any, schema: str, table: str) -> str:
    row = conn.execute("SELECT current_database()").fetchone()
    if row is None:
        raise RuntimeError("CATALOG_UNAVAILABLE")
    return ".".join('"' + str(p).replace('"', '""') + '"' for p in (row[0], schema, table))


@dataclass(frozen=True)
class PersistedAssociationEvidence:
    reader_version: str
    assessment_revision_id: str
    status: str
    reason_code: str
    active_revision_ids: tuple[str, ...] = ()
    successful_attempt_job_ids: tuple[str, ...] = ()
    association: PacketReferenceAssociation | None = None
    evidence_fingerprint: str | None = None
    publication_asserted: bool = False
    historical_validity_asserted: bool = False
    decision_eligibility_asserted: bool = False


def read_packet_assessment(
    bronze: Any,
    frame_silver: Any,
    reference_silver: Any,
    assessments: Any,
    *,
    assessment_revision_id: str,
) -> PersistedAssociationEvidence:
    """All connections caller-owned/read-only, no enclosing transactions.

    Resolve all graph rows without status/audit filtering. All linked attempts on
    the active pin must be terminal and correctly scoped; at least one must have
    succeeded. Failed/cancelled terminal attempts remain evidence, not success.
    Separate DB snapshots and fresh source reads are NOT a publication barrier.
    """
    if not valid_hash(assessment_revision_id):
        raise ValueError("EXACT_ASSESSMENT_REVISION_REQUIRED")
    ap = {r[2] for r in assessments.execute("PRAGMA database_list").fetchall() if r[2]}
    for source in (bronze, frame_silver, reference_silver):
        sp = {r[2] for r in source.execute("PRAGMA database_list").fetchall() if r[2]}
        if source is assessments or ap & sp:
            raise ValueError("SEPARATE_ASSESSMENT_DATABASE_REQUIRED")

    def blocked(reason: str, active: tuple[str, ...] = ()) -> PersistedAssociationEvidence:
        return PersistedAssociationEvidence(
            READER_VERSION,
            assessment_revision_id,
            "blocked",
            reason,
            active,
        )

    table = _name(assessments, "silver", "packet_reference_assessments")
    attempts_table = _name(assessments, "silver", "packet_reference_attempts")
    schema_table = _name(assessments, "silver", "packet_reference_schema_versions")
    jobs_table = _name(assessments, "medallion_audit", "jobs")
    events_table = _name(assessments, "medallion_audit", "job_events")
    audit_schema = _name(assessments, "medallion_audit", "schema_versions")
    contracts = _name(assessments, "medallion_audit", "dataset_contracts")
    assessments.execute("BEGIN TRANSACTION")
    try:
        schema = assessments.execute(f"SELECT version FROM {schema_table} LIMIT 2").fetchall()
        audit_versions = assessments.execute(
            f"SELECT version FROM {audit_schema} LIMIT 2"
        ).fetchall()
        if schema != [(1,)] or audit_versions != [(1,)]:
            assessments.execute("COMMIT")
            return blocked("UNSUPPORTED_ASSESSMENT_SCHEMA")
        pin = assessments.execute(
            f"SELECT input_revision_id FROM {table} WHERE revision_id=?",
            [assessment_revision_id],
        ).fetchone()
        if pin is None:
            assessments.execute("COMMIT")
            return blocked("ASSESSMENT_NOT_FOUND")
        history = assessments.execute(
            f"SELECT revision_id,input_revision_id,CASE WHEN "
            f"octet_length(encode(supersedes_json))<=100000 THEN supersedes_json ELSE NULL END "
            f"FROM {table} WHERE input_revision_id=? ORDER BY revision_id LIMIT ?",
            [pin[0], MAX_ASSESSMENTS + 1],
        ).fetchall()
        if len(history) > MAX_ASSESSMENTS:
            assessments.execute("COMMIT")
            return blocked("ASSESSMENT_HISTORY_LIMIT")
        try:
            nodes: list[AssessmentNode] = []
            for revision, group, links_json in history:
                links = _json(links_json)
                if not isinstance(links, list):
                    raise ValueError("INVALID_LINKS")
                nodes.append(AssessmentNode(revision, group, tuple(links)))
        except (ValueError, TypeError, RecursionError):
            assessments.execute("COMMIT")
            return blocked("INVALID_SUPERSESSION_EVIDENCE")
        graph = resolve_supersession(tuple(nodes), assessment_revision_id)
        if graph.reason_code != "ACTIVE_PINNED_ASSESSMENT":
            assessments.execute("COMMIT")
            return blocked(graph.reason_code, graph.active_revision_ids)
        record = assessments.execute(
            f"SELECT input_revision_id,source_observation_id,packet_ordinal,"
            f"reference_assessment_revision_id,store_version,association_version,status,"
            f"reason_code,association_fingerprint,CASE WHEN octet_length(encode(result_json))<=? "
            f"THEN result_json ELSE NULL END,published_at,effective_from,effective_to,first_job_id "
            f"FROM {table} WHERE revision_id=?",
            [MAX_RESULT_BYTES, assessment_revision_id],
        ).fetchone()
        linked = assessments.execute(
            f"SELECT a.job_id,j.command_name,j.scope_ref,j.config_hash,"
            f"(SELECT e.state FROM {events_table} e WHERE e.job_id=a.job_id "
            f"ORDER BY e.event_index DESC LIMIT 1) FROM {attempts_table} a "
            f"LEFT JOIN {jobs_table} j ON j.job_id=a.job_id "
            "WHERE a.revision_id=? ORDER BY a.job_id LIMIT ?",
            [assessment_revision_id, MAX_ATTEMPTS + 1],
        ).fetchall()
        contract = assessments.execute(
            f"SELECT fingerprint,contract_json FROM {contracts} "
            "WHERE dataset_name='silver.packet_reference_assessments' AND contract_version='1'"
        ).fetchone()
        assessments.execute("COMMIT")
    except BaseException:
        assessments.execute("ROLLBACK")
        raise
    active = graph.active_revision_ids
    if record is None:
        return blocked("PINNED_ASSESSMENT_DISAPPEARED", active)
    expected_contract = {
        "name": "silver.packet_reference_assessments",
        "version": "1",
        "layer": "silver",
        "write_policy": "append_revisions",
        "entity_keys": ["revision_id"],
        "required_columns": ["revision_id", "source_observation_id", "recorded_at"],
        "owner": "native_packet_reference",
    }
    if contract != (_hash(expected_contract), _canonical(expected_contract)):
        return blocked("ASSESSMENT_CONTRACT_NOT_VERIFIED", active)
    if record[4:6] != (STORE_VERSION, ASSOCIATION_VERSION):
        return blocked("UNSUPPORTED_ASSESSMENT_VERSION", active)
    if (
        not valid_hash(record[1])
        or not valid_hash(record[3])
        or not valid_hash(record[8])
        or type(record[2]) is not int
        or not 0 <= record[2] < 4096
    ):
        return blocked("INVALID_ASSESSMENT_SOURCE_PINS", active)
    versions = [STORE_VERSION, ASSOCIATION_VERSION]
    input_id = _hash([record[1], record[2], record[3], versions])
    if input_id != record[0] or _hash([input_id, record[8]]) != assessment_revision_id:
        return blocked("ASSESSMENT_IDENTITY_MISMATCH", active)
    if any(value is not None for value in record[10:13]):
        return blocked("UNSUPPORTED_TEMPORAL_CLAIMS", active)
    if len(linked) > MAX_ATTEMPTS:
        return blocked("ASSESSMENT_ATTEMPT_LIMIT", active)
    if not linked or record[13] not in {attempt[0] for attempt in linked}:
        return blocked("ASSESSMENT_ATTEMPT_LINEAGE_MISSING", active)
    succeeded: list[str] = []
    for job_id, command, scope, config, state in linked:
        if (command, scope, config) != (COMMAND, "sha256:" + input_id, _hash(versions)):
            return blocked("ASSESSMENT_ATTEMPT_AUDIT_MISMATCH", active)
        if state not in {"SUCCEEDED", "FAILED", "CANCELLED"}:
            return blocked("ASSESSMENT_ATTEMPT_NOT_TERMINAL", active)
        if state == "SUCCEEDED":
            succeeded.append(job_id)
    if not succeeded:
        return blocked("ASSESSMENT_NO_SUCCESSFUL_ATTEMPT", active)
    if record[9] is None:
        return blocked("ASSESSMENT_RESULT_LIMIT", active)
    try:
        value = _json(record[9])
        if not isinstance(value, dict) or _canonical(value) != record[9]:
            return blocked("INVALID_ASSESSMENT_RESULT", active)
        if (
            value["association_fingerprint"] != record[8]
            or _hash(dict(value, association_fingerprint=None)) != record[8]
            or [
                value[k]
                for k in (
                    "frame_revision_id",
                    "packet_ordinal",
                    "reference_assessment_revision_id",
                    "association_version",
                    "status",
                    "reason_code",
                )
            ]
            != [record[1], record[2], record[3], record[5], record[6], record[7]]
            or type(value["packet_ordinal"]) is not int
        ):
            return blocked("ASSESSMENT_RESULT_IDENTITY_MISMATCH", active)
    except (ValueError, TypeError, KeyError, RecursionError):
        return blocked("MALFORMED_ASSESSMENT_RESULT", active)
    current = associate_packet_reference(
        bronze,
        frame_silver,
        reference_silver,
        frame_revision_id=record[1],
        packet_ordinal=record[2],
        reference_assessment_revision_id=record[3],
    )
    current_json = _canonical(asdict(current))
    if current_json != record[9]:
        return blocked("CURRENT_ASSOCIATION_EVIDENCE_CHANGED", active)
    evidence_hash = _hash(
        [
            READER_VERSION,
            assessment_revision_id,
            active,
            linked,
            current_json,
        ]
    )
    return PersistedAssociationEvidence(
        READER_VERSION,
        assessment_revision_id,
        "verified_current",
        "SOURCE_RECOMPUTED",
        active,
        tuple(succeeded),
        current,
        evidence_hash,
    )
