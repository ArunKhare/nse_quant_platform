"""Targeted, bounded, nonexecuting recovery observations. No authority to repair."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from nse_quant.data_platform.feature_bundle import (
    BUNDLE_VERSION,
    MAX_BUNDLE_BYTES,
    decode_quote_bundle,
    valid_pin,
)
from nse_quant.data_platform.reference_supersession import AssessmentNode, resolve_supersession

PLANNER_VERSION = "quote-bundle-recovery-plan@1"
STAGING_VERSION = "quote-bundle-staging@1"
COMMAND = "stage.quote_feature_bundle@1"


@dataclass(frozen=True)
class RecoveryPolicy:
    max_history: int = 128
    max_jobs: int = 128
    max_directory_entries: int = 128
    max_artifact_bytes: int = MAX_BUNDLE_BYTES

    def __post_init__(self) -> None:
        for value, cap in (
            (self.max_history, 1001),
            (self.max_jobs, 1000),
            (self.max_directory_entries, 1000),
            (self.max_artifact_bytes, MAX_BUNDLE_BYTES),
        ):
            if type(value) is not int or not 1 <= value <= cap:
                raise ValueError("INVALID_RECOVERY_INSPECTION_BOUND")


DEFAULT_RECOVERY_POLICY = RecoveryPolicy()


@dataclass(frozen=True)
class RecoveryFinding:
    reason_code: str
    evidence_ref: str


@dataclass(frozen=True)
class BundleRecoveryPlan:
    plan_id: str
    planner_version: str
    bundle_id: str
    artifact_root: str
    status: str
    scope_complete: bool
    directory_scan_complete: bool
    metadata_present: bool
    artifact_observation: str
    artifact_hash_observed: str | None
    artifact_bytes_observed: int
    history_rows_observed: int
    audit_jobs_observed: int
    pending_file_refs: tuple[str, ...]
    findings: tuple[RecoveryFinding, ...]
    review_steps: tuple[str, ...]
    policy: RecoveryPolicy
    execution_permitted: bool = False
    global_inventory_performed: bool = False
    source_current_checked: bool = False
    publication_asserted: bool = False
    historical_validity_asserted: bool = False
    decision_eligibility_asserted: bool = False


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _ref(value: object) -> str:
    if (
        isinstance(value, str)
        and 1 <= len(value) <= 128
        and all(
            char in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-."
            for char in value
        )
    ):
        return value
    return "sha256:" + _hash(value)


def _name(conn: Any, schema: str, table: str) -> str:
    row = conn.execute("SELECT current_database()").fetchone()
    if row is None:
        raise RuntimeError("CATALOG_UNAVAILABLE")
    return ".".join('"' + str(part).replace('"', '""') + '"' for part in (row[0], schema, table))


def inspect_bundle_recovery(
    staging: Any,
    *,
    bundle_id: str,
    artifact_root: Path,
    policy: RecoveryPolicy = DEFAULT_RECOVERY_POLICY,
) -> BundleRecoveryPlan:
    """Read-only owned file-backed connection, no outer transaction.

    One explicit target, bounded history/jobs and directory-prefix observations;
    NOT a global inventory, source verifier, recovery executor or atomic snapshot.
    Pending files are names-only review candidates, never decoded/adopted.
    """
    if not valid_pin(bundle_id):
        raise ValueError("EXACT_RECOVERY_BUNDLE_PIN_REQUIRED")
    root = artifact_root.resolve()
    catalog = staging.execute("SELECT current_database()").fetchone()
    databases = staging.execute("PRAGMA database_list").fetchall()
    if catalog is None or not any(row[1] == catalog[0] and row[2] for row in databases):
        raise ValueError("FILE_BACKED_STAGING_DATABASE_REQUIRED")
    paths = [Path(row[2]).resolve() for row in databases if row[2]]
    if any(path == root or root in path.parents or path in root.parents for path in paths):
        raise ValueError("ARTIFACT_ROOT_MUST_BE_SEPARATE_FROM_DATABASES")
    settings = _name(staging, "gold", "quote_bundle_stage_schema")
    stages = _name(staging, "gold", "quote_bundle_stages")
    attempts = _name(staging, "gold", "quote_bundle_stage_attempts")
    jobs = _name(staging, "medallion_audit", "jobs")
    events = _name(staging, "medallion_audit", "job_events")
    audit_versions = _name(staging, "medallion_audit", "schema_versions")
    contracts = _name(staging, "medallion_audit", "dataset_contracts")
    staging.execute("BEGIN TRANSACTION")
    try:
        dedicated = (
            staging.execute(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_catalog=current_database() "
                "AND (table_schema NOT IN ('gold','medallion_audit') OR "
                "(table_schema='gold' AND table_name NOT IN "
                "('quote_bundle_stage_schema','quote_bundle_stages',"
                "'quote_bundle_stage_attempts'))) "
                "LIMIT 1"
            ).fetchone()
            is None
        )
        contract = staging.execute(
            f"SELECT fingerprint,contract_json FROM {contracts} "
            "WHERE dataset_name='gold.quote_bundle_stages' AND contract_version='1'"
        ).fetchone()
        binding = staging.execute(
            f"SELECT version,artifact_root FROM {settings} ORDER BY version LIMIT 2"
        ).fetchall()
        audit = staging.execute(f"SELECT version FROM {audit_versions} LIMIT 2").fetchall()
        row = staging.execute(
            f"SELECT input_revision_id,staging_version,feature_version,membership_fingerprint,"
            f"manifest_hash,manifest_bytes,member_count,artifact_name,seal_state,event_ts IS NULL,"
            f"published_at IS NULL,first_job_id FROM {stages} WHERE build_id=?",
            [bundle_id],
        ).fetchone()
        history: list[tuple[Any, ...]] = []
        if row is not None:
            history = staging.execute(
                f"SELECT build_id,CASE WHEN octet_length(encode(supersedes_json))<=100000 "
                f"THEN supersedes_json ELSE NULL END FROM {stages} "
                "WHERE input_revision_id=? ORDER BY build_id LIMIT ?",
                [row[0], policy.max_history + 1],
            ).fetchall()
        staging.execute("COMMIT")
    except BaseException:
        staging.execute("ROLLBACK")
        raise
    findings: list[RecoveryFinding] = []
    complete = True
    directory_complete = True
    pending: list[str] = []
    observed_hash = None
    observed_bytes = 0
    artifact_status = "NOT_INSPECTED"
    job_rows: list[Any] = []

    def note(code: str, reference: str = bundle_id) -> None:
        findings.append(RecoveryFinding(code, reference))

    bound = (
        dedicated
        and binding == [(1, str(root))]
        and audit == [(1,)]
        and BUNDLE_VERSION == "quote-feature-bundle@1"
    )
    if not bound:
        note("SCHEMA_OR_ROOT_BINDING_REVIEW_REQUIRED")
        complete = directory_complete = False
    history_complete = len(history) <= policy.max_history
    if not history_complete:
        note("HISTORY_COVERAGE_LIMIT")
        complete = False
    history = history[: policy.max_history]
    scope = row[0] if row is not None and valid_pin(row[0]) else None
    versions = [STAGING_VERSION, BUNDLE_VERSION]
    decoded = None
    if bound:
        if not root.is_dir():
            note("ARTIFACT_ROOT_MISSING_OR_NOT_DIRECTORY")
            complete = directory_complete = False
            artifact_status = "ROOT_UNAVAILABLE"
        else:
            target = root / (bundle_id + ".json")
            if target.is_symlink():
                artifact_status = "SYMLINK_NOT_FOLLOWED"
                note("SYMLINK_ARTIFACT_REVIEW_REQUIRED")
            else:
                try:
                    size = target.stat().st_size
                    if size > policy.max_artifact_bytes:
                        artifact_status = "NOT_READ_BYTE_LIMIT"
                        note("ARTIFACT_BYTE_LIMIT_REVIEW_REQUIRED")
                        complete = False
                    elif not target.is_file():
                        artifact_status = "NOT_REGULAR_FILE"
                        note("ARTIFACT_TYPE_REVIEW_REQUIRED")
                    else:
                        with target.open("rb") as handle:
                            raw = handle.read(min(policy.max_artifact_bytes + 1, size + 1))
                        observed_bytes = len(raw)
                        observed_hash = hashlib.sha256(raw).hexdigest()
                        if len(raw) != size:
                            artifact_status = "CHANGED_DURING_READ"
                            note("ARTIFACT_CHANGED_DURING_INSPECTION")
                            complete = False
                        else:
                            try:
                                decoded = decode_quote_bundle(raw, expected_bundle_id=bundle_id)
                                artifact_status = "CONTENT_VALID_NOT_SOURCE_VERIFIED"
                            except (ValueError, TypeError, RecursionError):
                                artifact_status = "CONTENT_INVALID"
                                note("ARTIFACT_CONTENT_REVIEW_REQUIRED")
                except FileNotFoundError:
                    artifact_status = "MISSING"
                    note(
                        "REGISTERED_ARTIFACT_MISSING" if row is not None else "TARGET_NOT_OBSERVED"
                    )
                except OSError:
                    artifact_status = "IO_ERROR"
                    note("ARTIFACT_IO_REVIEW_REQUIRED")
                    complete = False
            if row is None and artifact_status not in {"MISSING", "NOT_INSPECTED"}:
                note("ORPHAN_ARTIFACT_NO_ADOPTION_AUTHORITY")
            try:
                with os.scandir(root) as entries:
                    for index, entry in enumerate(entries):
                        if index >= policy.max_directory_entries:
                            directory_complete = False
                            note("DIRECTORY_PREFIX_COVERAGE_LIMIT")
                            break
                        if entry.name.startswith(".pending-bundle-"):
                            reference = (
                                "sha256:"
                                + hashlib.sha256(
                                    entry.name.encode("utf-8", errors="surrogatepass")
                                ).hexdigest()
                            )
                            pending.append(reference)
                            note("PENDING_FILE_REVIEW_CANDIDATE_NOT_INGESTIBLE", reference)
            except OSError:
                directory_complete = False
                note("DIRECTORY_IO_REVIEW_REQUIRED")
    if (
        bound
        and row is not None
        and (
            row[1:3] != (STAGING_VERSION, BUNDLE_VERSION)
            or row[4] != bundle_id
            or row[7] != bundle_id + ".json"
            or row[8] != "SEALED_NOT_PUBLISHED"
            or row[9] is not True
            or row[10] is not True
            or not valid_pin(row[0])
            or not valid_pin(row[3])
            or type(row[5]) is not int
            or not 1 <= row[5] <= MAX_BUNDLE_BYTES
            or type(row[6]) is not int
            or not 1 <= row[6] <= 64
        )
    ):
        note("STAGE_METADATA_REVIEW_REQUIRED")
    if decoded is not None:
        pins = tuple(member.build_id for member in decoded.members)
        actual_scope = _hash([versions, pins])
        if row is None:
            scope = actual_scope
        elif (row[0], row[3], row[5], row[6]) != (
            actual_scope,
            decoded.membership_fingerprint,
            observed_bytes,
            len(pins),
        ):
            note("STAGE_MANIFEST_DISAGREEMENT")
    if bound:
        staging.execute("BEGIN TRANSACTION")
        try:
            job_rows = staging.execute(
                f"SELECT j.job_id,j.command_name,j.scope_ref,j.config_hash,"
                f"(SELECT e.state FROM {events} e WHERE e.job_id=j.job_id "
                f"ORDER BY e.event_index DESC LIMIT 1),"
                f"EXISTS(SELECT 1 FROM {attempts} a WHERE a.job_id=j.job_id AND a.build_id=?),"
                f"j.actor_id,j.code_revision,"
                f"EXISTS(SELECT 1 FROM {attempts} a WHERE a.job_id=j.job_id) "
                f"FROM {jobs} j WHERE (j.command_name=? AND j.scope_ref=?) OR "
                f"EXISTS(SELECT 1 FROM {attempts} a WHERE a.job_id=j.job_id AND a.build_id=?) "
                "ORDER BY j.job_id LIMIT ?",
                [
                    bundle_id,
                    COMMAND,
                    "sha256:" + scope if scope is not None else None,
                    bundle_id,
                    policy.max_jobs + 1,
                ],
            ).fetchall()
            linked = staging.execute(
                f"SELECT a.job_id FROM {attempts} a LEFT JOIN {jobs} j ON j.job_id=a.job_id "
                "WHERE a.build_id=? AND j.job_id IS NULL ORDER BY a.job_id LIMIT ?",
                [bundle_id, policy.max_jobs + 1],
            ).fetchall()
            staging.execute("COMMIT")
        except BaseException:
            staging.execute("ROLLBACK")
            raise
        if len(job_rows) > policy.max_jobs or len(linked) > policy.max_jobs:
            note("AUDIT_COVERAGE_LIMIT")
            complete = False
        for missing in linked[: policy.max_jobs]:
            note("LINKED_AUDIT_JOB_NOT_OBSERVED", _ref(missing[0]))
        job_rows = job_rows[: policy.max_jobs]
        successful = False
        first_seen = False
        config = _hash([versions, str(root)])
        for audit_row in job_rows:
            (job, command, job_scope, job_config, state, attached, actor, revision, any_link) = (
                audit_row
            )
            reference = _ref(job)
            if row is not None and job == row[11] and attached:
                first_seen = True
            if (
                not isinstance(actor, str)
                or not actor.strip()
                or (not isinstance(revision, str) or not revision.strip())
                or command != COMMAND
                or job_config != config
                or (scope is not None and job_scope != "sha256:" + scope)
            ):
                note("AUDIT_IDENTITY_REVIEW_REQUIRED", reference)
            if state not in {"SUCCEEDED", "FAILED", "CANCELLED"}:
                note("AUDIT_NONTERMINAL_OR_UNKNOWN_REVIEW_REQUIRED", reference)
            elif state != "SUCCEEDED":
                note("FAILED_OR_CANCELLED_JOB_REVIEW_REQUIRED", reference)
            if not any_link:
                note("UNLINKED_STAGE_JOB_REVIEW_REQUIRED", reference)
            if attached and state == "SUCCEEDED":
                successful = True
        if row is not None and not first_seen:
            note("FIRST_JOB_LINK_NOT_OBSERVED")
        if row is not None and not successful:
            note("NO_SUCCESSFUL_LINKED_ATTEMPT_OBSERVED")
    if row is not None:
        expected_contract = {
            "name": "gold.quote_bundle_stages",
            "version": "1",
            "layer": "gold",
            "write_policy": "versioned_builds",
            "entity_keys": ["build_id"],
            "required_columns": ["build_id", "event_ts", "published_at", "feature_version"],
            "owner": "native_quote_bundle_staging",
        }
        if contract != (_hash(expected_contract), _canonical(expected_contract)):
            note("STAGE_CONTRACT_REVIEW_REQUIRED")
        try:

            def no_duplicates(items: list[tuple[str, Any]]) -> dict[str, Any]:
                result: dict[str, Any] = {}
                for key, value in items:
                    if key in result:
                        raise ValueError("DUPLICATE_HISTORY_KEY")
                    result[key] = value
                return result

            nodes: list[AssessmentNode] = []
            for identity, links_json in history:
                parsed = json.loads(links_json, object_pairs_hook=no_duplicates)
                if not isinstance(parsed, list):
                    raise ValueError("INVALID_HISTORY_LINKS")
                nodes.append(AssessmentNode(identity, row[0], tuple(parsed)))
            if history_complete:
                graph = resolve_supersession(tuple(nodes), bundle_id)
                if graph.reason_code != "ACTIVE_PINNED_ASSESSMENT":
                    note("HISTORY_" + graph.reason_code)
        except (ValueError, TypeError, RecursionError):
            note("HISTORY_EVIDENCE_REVIEW_REQUIRED")
    complete = complete and directory_complete
    ordered = tuple(
        sorted(set(findings), key=lambda finding: (finding.reason_code, finding.evidence_ref))
    )
    steps: tuple[str, ...] = (
        "PRESERVE_EXISTING_EVIDENCE",
        "REVIEW_TARGET_METADATA_ARTIFACT_AND_AUDIT",
        "DO_NOT_ADOPT_RESEAL_DELETE_OR_FORCE_SUCCESS",
        "REQUIRE_SEPARATE_APPROVED_RECOVERY",
    )
    if not ordered and complete:
        steps = ("NO_REPAIR_PROPOSED", "USE_STAGED_CONSUMER_FOR_CURRENT_SOURCE_VERIFICATION")
    status = (
        "INCOMPLETE_REVIEW_REQUIRED"
        if not complete
        else ("REVIEW_REQUIRED" if ordered else "NO_TARGET_FINDINGS")
    )
    plan = BundleRecoveryPlan(
        "",
        PLANNER_VERSION,
        bundle_id,
        str(root),
        status,
        complete,
        directory_complete,
        row is not None,
        artifact_status,
        observed_hash,
        observed_bytes,
        len(history),
        len(job_rows),
        tuple(sorted(pending)),
        ordered,
        steps,
        policy,
    )
    return BundleRecoveryPlan(
        **dict(asdict(plan), policy=policy, findings=ordered, plan_id=_hash(asdict(plan)))
    )
