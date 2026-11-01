"""Audited bundle artifact staging, explicitly separate from publication."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.bundle_artifacts import BundleArtifacts
from nse_quant.data_platform.contracts import DatasetContract, Layer, WritePolicy
from nse_quant.data_platform.feature_bundle import (
    BUNDLE_VERSION,
    MAX_MEMBERS,
    encode_quote_bundle,
    valid_pin,
)
from nse_quant.data_platform.quote_bundle_assembly import assemble_quote_bundle

STAGING_VERSION = "quote-bundle-staging@1"
COMMAND = "stage.quote_feature_bundle@1"
SEAL_STATE = "SEALED_NOT_PUBLISHED"
MAX_HISTORY = 1000


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _paths(conn: Any) -> set[Path]:
    return {
        Path(row[2]).resolve() for row in conn.execute("PRAGMA database_list").fetchall() if row[2]
    }


def _name(conn: Any, table: str) -> str:
    row = conn.execute("SELECT current_database()").fetchone()
    if row is None:
        raise RuntimeError("CATALOG_UNAVAILABLE")
    return ".".join('"' + str(part).replace('"', '""') + '"' for part in (row[0], "gold", table))


def _same(first: Path, second: Path) -> bool:
    return first == second or (first.exists() and second.exists() and first.samefile(second))


def stage_quote_bundle(
    bronze: Any,
    frame_silver: Any,
    reference_silver: Any,
    assessments: Any,
    gold: Any,
    staging: Any,
    *,
    build_ids: tuple[str, ...],
    artifact_root: Path,
    actor_id: str,
    code_revision: str,
    initialize: bool = False,
) -> dict[str, object]:
    """Inputs read-only; file-backed staging DB single-owner, no outer transaction.

    File commit, metadata commit and final audit success are distinct. No repair,
    orphan adoption, automatic reseal/retry or publication is performed.
    """
    if (
        not isinstance(build_ids, tuple)
        or not 1 <= len(build_ids) <= MAX_MEMBERS
        or any(not valid_pin(pin) for pin in build_ids)
        or len(set(build_ids)) != len(build_ids)
    ):
        raise ValueError("EXPLICIT_UNIQUE_BOUNDED_BUILD_PINS_REQUIRED")
    if BUNDLE_VERSION != "quote-feature-bundle@1":
        raise ValueError("UNSUPPORTED_STAGING_BUNDLE_VERSION")
    if not actor_id.strip() or not code_revision.strip():
        raise ValueError("EXECUTION_IDENTITIES_REQUIRED")
    pins = tuple(sorted(build_ids))
    artifacts = BundleArtifacts(artifact_root)
    sources = (bronze, frame_silver, reference_silver, assessments, gold)
    catalog = staging.execute("SELECT current_database()").fetchone()
    databases = staging.execute("PRAGMA database_list").fetchall()
    if catalog is None or not any(row[1] == catalog[0] and row[2] for row in databases):
        raise ValueError("FILE_BACKED_STAGING_DATABASE_REQUIRED")
    outputs = _paths(staging)
    all_paths = set(outputs)
    for source in sources:
        inputs = _paths(source)
        if source is staging or any(_same(out, src) for out in outputs for src in inputs):
            raise ValueError("SEPARATE_BUNDLE_STAGING_DATABASE_REQUIRED")
        all_paths.update(inputs)
    if any(
        path == artifacts.root or artifacts.root in path.parents or path in artifacts.root.parents
        for path in all_paths
    ):
        raise ValueError("ARTIFACT_ROOT_MUST_BE_SEPARATE_FROM_DATABASES")
    if staging.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_catalog=current_database() "
        "AND (table_schema NOT IN ('gold','medallion_audit') OR "
        "(table_schema='gold' AND table_name NOT IN "
        "('quote_bundle_stage_schema','quote_bundle_stages','quote_bundle_stage_attempts'))) "
        "LIMIT 1"
    ).fetchone():
        raise ValueError("DEDICATED_BUNDLE_STAGING_DATABASE_REQUIRED")
    versions = [STAGING_VERSION, BUNDLE_VERSION]
    scope = _hash([versions, pins])
    config = _hash([versions, str(artifacts.root)])
    ledger = AuditLedger(staging)
    if initialize:
        ledger.initialize()
    job = ledger.plan_job(
        command_name=COMMAND,
        actor_id=actor_id,
        scope_ref="sha256:" + scope,
        code_revision=code_revision,
        config_hash=config,
    )
    settings = _name(staging, "quote_bundle_stage_schema")
    stages = _name(staging, "quote_bundle_stages")
    attempts = _name(staging, "quote_bundle_stage_attempts")
    with ledger.execution(job):
        if initialize:
            staging.execute("BEGIN TRANSACTION")
            try:
                staging.execute(f"CREATE SCHEMA IF NOT EXISTS {stages.rsplit('.', 1)[0]}")
                staging.execute(
                    f"CREATE TABLE IF NOT EXISTS {settings} ("
                    "version INTEGER PRIMARY KEY,artifact_root VARCHAR NOT NULL)"
                )
                existing = staging.execute(
                    f"SELECT version,artifact_root FROM {settings}"
                ).fetchall()
                if existing and existing != [(1, str(artifacts.root))]:
                    raise ValueError("STAGING_SCHEMA_OR_ROOT_BINDING_MISMATCH")
                if not existing:
                    staging.execute(f"INSERT INTO {settings} VALUES (1,?)", [str(artifacts.root)])
                staging.execute(f"""CREATE TABLE IF NOT EXISTS {stages} (
                    build_id VARCHAR PRIMARY KEY,input_revision_id VARCHAR NOT NULL,
                    staging_version VARCHAR NOT NULL,feature_version VARCHAR NOT NULL,
                    membership_fingerprint VARCHAR NOT NULL,manifest_hash VARCHAR NOT NULL,
                    manifest_bytes BIGINT NOT NULL,member_count INTEGER NOT NULL,
                    artifact_name VARCHAR NOT NULL,seal_state VARCHAR NOT NULL,
                    supersedes_json VARCHAR NOT NULL,event_ts TIMESTAMPTZ,
                    published_at TIMESTAMPTZ,recorded_at TIMESTAMPTZ NOT NULL,
                    first_job_id VARCHAR NOT NULL)""")
                staging.execute(f"""CREATE TABLE IF NOT EXISTS {attempts} (
                    job_id VARCHAR PRIMARY KEY,build_id VARCHAR NOT NULL,
                    recorded_at TIMESTAMPTZ NOT NULL)""")
                staging.execute("COMMIT")
            except BaseException:
                staging.execute("ROLLBACK")
                raise
        binding = staging.execute(
            f"SELECT version,artifact_root FROM {settings} LIMIT 2"
        ).fetchall()
        if binding != [(1, str(artifacts.root))]:
            raise ValueError("STAGING_SCHEMA_OR_ROOT_BINDING_MISMATCH")
        if (
            not artifacts.root.exists()
            and staging.execute(f"SELECT 1 FROM {stages} LIMIT 1").fetchone() is not None
        ):
            raise ValueError("STAGING_ARTIFACT_ROOT_MISSING_REVIEW_REQUIRED")
        ledger.register_contract(
            DatasetContract(
                name="gold.quote_bundle_stages",
                version="1",
                layer=Layer.GOLD,
                write_policy=WritePolicy.VERSIONED_BUILDS,
                entity_keys=("build_id",),
                required_columns=("build_id", "event_ts", "published_at", "feature_version"),
                owner="native_quote_bundle_staging",
            )
        )
        bundle = assemble_quote_bundle(*sources, build_ids=pins)
        raw = encode_quote_bundle(bundle)
        if tuple(member.build_id for member in bundle.members) != pins:
            raise ValueError("STAGED_BUNDLE_MEMBERSHIP_MISMATCH")
        expected = (
            scope,
            STAGING_VERSION,
            BUNDLE_VERSION,
            bundle.membership_fingerprint,
            bundle.bundle_id,
            len(raw),
            len(pins),
            bundle.bundle_id + ".json",
            SEAL_STATE,
            None,
            None,
        )
        previous = staging.execute(
            f"SELECT input_revision_id,staging_version,feature_version,membership_fingerprint,"
            f"manifest_hash,manifest_bytes,member_count,artifact_name,seal_state,"
            f"event_ts,published_at "
            f"FROM {stages} WHERE build_id=?",
            [bundle.bundle_id],
        ).fetchone()
        history: list[tuple[Any, ...]] = []
        if previous is None:
            history = staging.execute(
                f"SELECT build_id FROM {stages} WHERE input_revision_id=? "
                "ORDER BY build_id LIMIT ?",
                [scope, MAX_HISTORY + 1],
            ).fetchall()
            if len(history) > MAX_HISTORY:
                raise ValueError("BUNDLE_STAGE_HISTORY_LIMIT")
        exists = artifacts.exists(bundle.bundle_id)
        if previous is not None:
            if previous != expected:
                raise ValueError("STAGED_BUNDLE_CONTENT_MISMATCH")
            if not exists:
                raise ValueError("STAGED_ARTIFACT_MISSING_REVIEW_REQUIRED")
            if artifacts.read_exact(bundle.bundle_id) != raw:
                raise ValueError("STAGED_ARTIFACT_CONTENT_MISMATCH")
        else:
            if exists:
                raise ValueError("ORPHAN_BUNDLE_ARTIFACT_REVIEW_REQUIRED")
            artifacts.write_new(raw, bundle_id=bundle.bundle_id)
            if artifacts.read_exact(bundle.bundle_id) != raw:
                raise ValueError("STAGED_ARTIFACT_CONTENT_MISMATCH")
        staging.execute("BEGIN TRANSACTION")
        try:
            if previous is None:
                staging.execute(
                    f"INSERT INTO {stages} VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [
                        bundle.bundle_id,
                        *expected[:9],
                        _canonical([row[0] for row in history]),
                        None,
                        None,
                        datetime.now(UTC),
                        job,
                    ],
                )
            staging.execute(
                f"INSERT INTO {attempts} VALUES (?,?,?)", [job, bundle.bundle_id, datetime.now(UTC)]
            )
            staging.execute("COMMIT")
        except BaseException:
            staging.execute("ROLLBACK")
            raise
    return {
        "bundle_id": bundle.bundle_id,
        "job_id": job,
        "input_revision_id": scope,
        "inserted": previous is None,
        "status": SEAL_STATE,
        "published": False,
        "historical_validity_asserted": False,
        "decision_eligibility_asserted": False,
    }
