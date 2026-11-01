"""Read-only staged-bundle verification. Sealed/current is never published/eligible."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from nse_quant.data_platform.bundle_artifacts import BundleArtifacts
from nse_quant.data_platform.feature_bundle import (
    BUNDLE_VERSION,
    MAX_BUNDLE_BYTES,
    MAX_MEMBERS,
    QuoteFeatureBundle,
    decode_quote_bundle,
    encode_quote_bundle,
    valid_pin,
)
from nse_quant.data_platform.quote_bundle_assembly import (
    BundleAssemblyRejected,
    assemble_quote_bundle,
)
from nse_quant.data_platform.quote_bundle_staging import COMMAND, SEAL_STATE, STAGING_VERSION
from nse_quant.data_platform.reference_supersession import (
    MAX_ASSESSMENTS,
    AssessmentNode,
    resolve_supersession,
)

READER_VERSION = "staged-quote-bundle-consumer@1"
MAX_ATTEMPTS = 1000


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _json(raw: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("DUPLICATE_STAGE_JSON_KEY")
            result[key] = value
        return result

    def invalid(_value: str) -> Any:
        raise ValueError("NONFINITE_STAGE_JSON")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def _name(conn: Any, schema: str, table: str) -> str:
    row = conn.execute("SELECT current_database()").fetchone()
    if row is None:
        raise RuntimeError("CATALOG_UNAVAILABLE")
    return ".".join('"' + str(part).replace('"', '""') + '"' for part in (row[0], schema, table))


def _paths(conn: Any) -> set[Path]:
    return {
        Path(row[2]).resolve() for row in conn.execute("PRAGMA database_list").fetchall() if row[2]
    }


@dataclass(frozen=True)
class _Snapshot:
    dedicated: bool
    binding: tuple[Any, ...]
    audit_versions: tuple[Any, ...]
    group: str | None
    history: tuple[Any, ...]
    record: tuple[Any, ...] | None
    contract: tuple[Any, ...] | None
    attempts: tuple[Any, ...]


def _snapshot(conn: Any, bundle_id: str) -> _Snapshot:
    settings = _name(conn, "gold", "quote_bundle_stage_schema")
    stages = _name(conn, "gold", "quote_bundle_stages")
    links = _name(conn, "gold", "quote_bundle_stage_attempts")
    versions = _name(conn, "medallion_audit", "schema_versions")
    contracts = _name(conn, "medallion_audit", "dataset_contracts")
    jobs = _name(conn, "medallion_audit", "jobs")
    events = _name(conn, "medallion_audit", "job_events")
    conn.execute("BEGIN TRANSACTION")
    try:
        dedicated = (
            conn.execute(
                "SELECT 1 FROM information_schema.tables WHERE table_catalog=current_database() "
                "AND (table_schema NOT IN ('gold','medallion_audit') OR "
                "(table_schema='gold' AND table_name NOT IN "
                "('quote_bundle_stage_schema','quote_bundle_stages',"
                "'quote_bundle_stage_attempts'))) "
                "LIMIT 1"
            ).fetchone()
            is None
        )
        binding = tuple(
            conn.execute(
                f"SELECT version,artifact_root FROM {settings} ORDER BY version LIMIT 2"
            ).fetchall()
        )
        audit_versions = tuple(
            conn.execute(f"SELECT version FROM {versions} ORDER BY version LIMIT 2").fetchall()
        )
        pin = conn.execute(
            f"SELECT input_revision_id FROM {stages} WHERE build_id=?",
            [bundle_id],
        ).fetchone()
        group = pin[0] if pin is not None else None
        history: tuple[Any, ...] = ()
        record: tuple[Any, ...] | None = None
        contract: tuple[Any, ...] | None = None
        attempts: tuple[Any, ...] = ()
        if pin is not None:
            history = tuple(
                conn.execute(
                    f"SELECT build_id,input_revision_id,CASE WHEN "
                    f"octet_length(encode(supersedes_json))<=100000 "
                    f"THEN supersedes_json ELSE NULL END "
                    f"FROM {stages} WHERE input_revision_id=? ORDER BY build_id LIMIT ?",
                    [group, MAX_ASSESSMENTS + 1],
                ).fetchall()
            )
            record = conn.execute(
                f"SELECT input_revision_id,staging_version,feature_version,membership_fingerprint,"
                f"manifest_hash,manifest_bytes,member_count,artifact_name,seal_state,event_ts,"
                f"published_at,first_job_id FROM {stages} WHERE build_id=?",
                [bundle_id],
            ).fetchone()
            contract = conn.execute(
                f"SELECT fingerprint,contract_json FROM {contracts} "
                "WHERE dataset_name='gold.quote_bundle_stages' AND contract_version='1'"
            ).fetchone()
            attempts = tuple(
                conn.execute(
                    f"SELECT a.job_id,j.command_name,j.scope_ref,j.config_hash,j.actor_id,"
                    f"j.code_revision,(SELECT e.state FROM {events} e WHERE e.job_id=a.job_id "
                    f"ORDER BY e.event_index DESC LIMIT 1) FROM {links} a "
                    f"LEFT JOIN {jobs} j ON j.job_id=a.job_id WHERE a.build_id=? "
                    "ORDER BY a.job_id LIMIT ?",
                    [bundle_id, MAX_ATTEMPTS + 1],
                ).fetchall()
            )
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    return _Snapshot(dedicated, binding, audit_versions, group, history, record, contract, attempts)


@dataclass(frozen=True)
class StagedQuoteBundleEvidence:
    reader_version: str
    bundle_id: str
    status: str
    reason_code: str
    active_bundle_ids: tuple[str, ...] = ()
    successful_attempt_job_ids: tuple[str, ...] = ()
    bundle: QuoteFeatureBundle | None = None
    evidence_fingerprint: str | None = None
    publication_asserted: bool = False
    historical_validity_asserted: bool = False
    decision_eligibility_asserted: bool = False


def read_staged_quote_bundle(
    bronze: Any,
    frame_silver: Any,
    reference_silver: Any,
    assessments: Any,
    gold: Any,
    staging: Any,
    *,
    bundle_id: str,
    artifact_root: Path,
) -> StagedQuoteBundleEvidence:
    """Owned read-only connections; no outer transactions, initialization or repair.

    Full graph before outcome/audit filtering. Verify exact staged artifact and
    linked audits, reassemble source snapshots, then recheck metadata/artifact.
    These observed stability checks are NOT an atomic multi-resource barrier.
    """
    if not valid_pin(bundle_id):
        raise ValueError("EXACT_STAGED_BUNDLE_PIN_REQUIRED")
    artifacts = BundleArtifacts(artifact_root)
    sources = (bronze, frame_silver, reference_silver, assessments, gold)
    current = staging.execute("SELECT current_database()").fetchone()
    databases = staging.execute("PRAGMA database_list").fetchall()
    if current is None or not any(row[1] == current[0] and row[2] for row in databases):
        raise ValueError("FILE_BACKED_STAGING_DATABASE_REQUIRED")
    stage_paths = _paths(staging)
    all_paths = set(stage_paths)
    for source in sources:
        paths = _paths(source)
        if source is staging or any(
            first == second or (first.exists() and second.exists() and first.samefile(second))
            for first in stage_paths
            for second in paths
        ):
            raise ValueError("SEPARATE_BUNDLE_STAGING_DATABASE_REQUIRED")
        all_paths.update(paths)
    if any(
        path == artifacts.root or artifacts.root in path.parents or path in artifacts.root.parents
        for path in all_paths
    ):
        raise ValueError("ARTIFACT_ROOT_MUST_BE_SEPARATE_FROM_DATABASES")

    def blocked(reason: str, active: tuple[str, ...] = ()) -> StagedQuoteBundleEvidence:
        return StagedQuoteBundleEvidence(READER_VERSION, bundle_id, "blocked", reason, active)

    snap = _snapshot(staging, bundle_id)
    if not snap.dedicated:
        return blocked("DEDICATED_STAGE_DATABASE_NOT_VERIFIED")
    if snap.binding != ((1, str(artifacts.root)),) or snap.audit_versions != ((1,),):
        return blocked("STAGE_SCHEMA_OR_ROOT_BINDING_NOT_VERIFIED")
    if snap.group is None:
        return blocked(
            "ORPHAN_ARTIFACT_REVIEW_REQUIRED"
            if artifacts.exists(bundle_id)
            else "STAGED_BUNDLE_NOT_FOUND"
        )
    if len(snap.history) > MAX_ASSESSMENTS:
        return blocked("STAGE_HISTORY_LIMIT")
    try:
        nodes: list[AssessmentNode] = []
        for identity, group, raw_links in snap.history:
            parsed = _json(raw_links)
            if not isinstance(parsed, list):
                raise ValueError("INVALID_LINKS")
            nodes.append(AssessmentNode(identity, group, tuple(parsed)))
    except (ValueError, TypeError, RecursionError):
        return blocked("INVALID_STAGE_HISTORY")
    graph = resolve_supersession(tuple(nodes), bundle_id)
    if graph.reason_code != "ACTIVE_PINNED_ASSESSMENT":
        return blocked("STAGE_" + graph.reason_code, graph.active_revision_ids)
    active = graph.active_revision_ids
    record = snap.record
    if record is None:
        return blocked("STAGE_RECORD_DISAPPEARED", active)
    contract = {
        "name": "gold.quote_bundle_stages",
        "version": "1",
        "layer": "gold",
        "write_policy": "versioned_builds",
        "entity_keys": ["build_id"],
        "required_columns": ["build_id", "event_ts", "published_at", "feature_version"],
        "owner": "native_quote_bundle_staging",
    }
    if snap.contract != (_hash(contract), _canonical(contract)):
        return blocked("STAGE_CONTRACT_NOT_VERIFIED", active)
    if (
        STAGING_VERSION != "quote-bundle-staging@1"
        or BUNDLE_VERSION != "quote-feature-bundle@1"
        or COMMAND != "stage.quote_feature_bundle@1"
        or SEAL_STATE != "SEALED_NOT_PUBLISHED"
        or record[1:3] != (STAGING_VERSION, BUNDLE_VERSION)
        or record[8] != SEAL_STATE
    ):
        return blocked("UNSUPPORTED_STAGE_VERSION_OR_STATE", active)
    if (
        not valid_pin(record[0])
        or not valid_pin(record[3])
        or record[4] != bundle_id
        or type(record[5]) is not int
        or not 1 <= record[5] <= MAX_BUNDLE_BYTES
        or type(record[6]) is not int
        or not 1 <= record[6] <= MAX_MEMBERS
        or record[7] != bundle_id + ".json"
    ):
        return blocked("STAGE_ARTIFACT_METADATA_MISMATCH", active)
    if record[9] is not None or record[10] is not None:
        return blocked("UNSUPPORTED_STAGE_TEMPORAL_CLAIMS", active)
    if len(snap.attempts) > MAX_ATTEMPTS:
        return blocked("STAGE_ATTEMPT_LIMIT", active)
    if not snap.attempts or record[11] not in {attempt[0] for attempt in snap.attempts}:
        return blocked("STAGE_ATTEMPT_LINEAGE_MISSING", active)
    versions = [STAGING_VERSION, BUNDLE_VERSION]
    config = _hash([versions, str(artifacts.root)])
    succeeded: list[str] = []
    for job, command, scope, config_hash, actor, revision, state in snap.attempts:
        if (
            not isinstance(job, str)
            or not job.strip()
            or (command, scope, config_hash) != (COMMAND, "sha256:" + record[0], config)
            or not isinstance(actor, str)
            or not actor.strip()
            or not isinstance(revision, str)
            or not revision.strip()
        ):
            return blocked("STAGE_ATTEMPT_AUDIT_MISMATCH", active)
        if state not in {"SUCCEEDED", "FAILED", "CANCELLED"}:
            return blocked("STAGE_ATTEMPT_NOT_TERMINAL", active)
        if state == "SUCCEEDED":
            succeeded.append(job)
    if not succeeded:
        return blocked("STAGE_NO_SUCCESSFUL_ATTEMPT", active)
    if not artifacts.root.is_dir():
        return blocked("STAGE_ARTIFACT_ROOT_MISSING_REVIEW_REQUIRED", active)
    try:
        raw = artifacts.read_exact(bundle_id)
        bundle = decode_quote_bundle(raw, expected_bundle_id=bundle_id)
    except FileNotFoundError:
        return blocked("STAGED_ARTIFACT_MISSING_REVIEW_REQUIRED", active)
    except (ValueError, IsADirectoryError):
        return blocked("STAGED_ARTIFACT_INVALID_REVIEW_REQUIRED", active)
    pins = tuple(member.build_id for member in bundle.members)
    if (
        bundle.membership_fingerprint != record[3]
        or len(raw) != record[5]
        or len(pins) != record[6]
        or _hash([versions, pins]) != record[0]
    ):
        return blocked("STAGE_MANIFEST_METADATA_MISMATCH", active)
    try:
        assembled = assemble_quote_bundle(*sources, build_ids=pins)
    except BundleAssemblyRejected:
        return blocked("STAGED_BUNDLE_SOURCE_REJECTED", active)
    if encode_quote_bundle(assembled) != raw:
        return blocked("STAGED_BUNDLE_CURRENT_EVIDENCE_CHANGED", active)
    if _snapshot(staging, bundle_id) != snap:
        return blocked("STAGING_METADATA_CHANGED_DURING_VERIFICATION", active)
    try:
        if artifacts.read_exact(bundle_id) != raw:
            return blocked("STAGING_ARTIFACT_CHANGED_DURING_VERIFICATION", active)
    except FileNotFoundError:
        return blocked("STAGED_ARTIFACT_MISSING_REVIEW_REQUIRED", active)
    except (ValueError, IsADirectoryError):
        return blocked("STAGED_ARTIFACT_INVALID_REVIEW_REQUIRED", active)
    fingerprint = _hash(
        [
            READER_VERSION,
            bundle_id,
            str(artifacts.root),
            asdict(snap),
            hashlib.sha256(raw).hexdigest(),
        ]
    )
    return StagedQuoteBundleEvidence(
        READER_VERSION,
        bundle_id,
        "verified_current",
        "STAGE_AND_SOURCES_RECOMPUTED",
        active,
        tuple(succeeded),
        bundle,
        fingerprint,
    )
