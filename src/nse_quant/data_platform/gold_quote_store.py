"""Audited immutable native Gold builds; persistence is never publication."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.contracts import DatasetContract, Layer, WritePolicy
from nse_quant.data_platform.gold_quote_features import (
    DEFINITION,
    DEFINITION_FINGERPRINT,
    FEATURE_VERSION,
    build_quote_price_candidate,
)

STORE_VERSION = "gold-provider-price-builds@1"
COMMAND = "build.provider_quote_prices@1"
MAX_RESULT_BYTES = 1_048_576
MAX_HISTORY = 1000


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _pin(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _name(conn: Any, table: str) -> str:
    row = conn.execute("SELECT current_database()").fetchone()
    if row is None:
        raise RuntimeError("CATALOG_UNAVAILABLE")
    return ".".join('"' + str(p).replace('"', '""') + '"' for p in (row[0], "gold", table))


def _paths(conn: Any) -> set[str]:
    return {str(row[2]) for row in conn.execute("PRAGMA database_list").fetchall() if row[2]}


def _time(raw: str | None) -> datetime | None:
    if raw is None:
        return None
    value = datetime.fromisoformat(raw)
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("AWARE_FEATURE_TIME_REQUIRED")
    value = value.astimezone(UTC)
    if value.isoformat() != raw:
        raise ValueError("CANONICAL_UTC_FEATURE_TIME_REQUIRED")
    return value


def persist_quote_price_build(
    bronze: Any,
    frame_silver: Any,
    reference_silver: Any,
    assessments: Any,
    gold: Any,
    *,
    assessment_revision_id: str,
    actor_id: str,
    code_revision: str,
    initialize: bool = False,
) -> dict[str, object]:
    """Freshly compute under audit; never import caller-supplied feature results.

    Inputs caller-owned/read-only, output single-owner writable, no outer
    transactions. Output is separate from ALL inputs. An attempt link/domain
    commit alone does not establish terminal audit success or publication.
    """
    if not _pin(assessment_revision_id):
        raise ValueError("EXACT_ASSESSMENT_REVISION_REQUIRED")
    if not actor_id.strip() or not code_revision.strip():
        raise ValueError("EXECUTION_IDENTITIES_REQUIRED")
    output_paths = _paths(gold)
    for source in (bronze, frame_silver, reference_silver, assessments):
        if source is gold or output_paths & _paths(source):
            raise ValueError("SEPARATE_GOLD_DATABASE_REQUIRED")
    if gold.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_catalog=current_database() "
        "AND table_schema NOT IN ('gold','medallion_audit') LIMIT 1"
    ).fetchone():
        raise ValueError("DEDICATED_GOLD_REQUIRED")
    definition_json = _canonical(DEFINITION)
    if len(definition_json.encode()) > 32768:
        raise ValueError("FEATURE_DEFINITION_LIMIT")
    if _hash(DEFINITION) != DEFINITION_FINGERPRINT:
        raise ValueError("FEATURE_DEFINITION_FINGERPRINT_MISMATCH")
    versions = [STORE_VERSION, FEATURE_VERSION, DEFINITION_FINGERPRINT]
    input_id = _hash([assessment_revision_id, versions])
    ledger = AuditLedger(gold)
    if initialize:
        ledger.initialize()
    job = ledger.plan_job(
        command_name=COMMAND,
        actor_id=actor_id,
        scope_ref="sha256:" + input_id,
        code_revision=code_revision,
        config_hash=_hash(versions),
    )
    builds = _name(gold, "quote_price_builds")
    definitions = _name(gold, "quote_price_definitions")
    attempts = _name(gold, "quote_price_build_attempts")
    schema_versions = _name(gold, "quote_price_schema_versions")
    with ledger.execution(job):
        if initialize:
            gold.execute("BEGIN TRANSACTION")
            try:
                gold.execute(f"CREATE SCHEMA IF NOT EXISTS {builds.rsplit('.', 1)[0]}")
                gold.execute(
                    f"CREATE TABLE IF NOT EXISTS {schema_versions} (version INTEGER PRIMARY KEY)"
                )
                existing = gold.execute(f"SELECT version FROM {schema_versions}").fetchall()
                if existing and existing != [(1,)]:
                    raise ValueError("UNSUPPORTED_GOLD_QUOTE_SCHEMA")
                if not existing:
                    gold.execute(f"INSERT INTO {schema_versions} VALUES (1)")
                gold.execute(f"""CREATE TABLE IF NOT EXISTS {definitions} (
                    feature_version VARCHAR PRIMARY KEY, definition_fingerprint VARCHAR NOT NULL,
                    definition_json VARCHAR NOT NULL, recorded_at TIMESTAMPTZ NOT NULL,
                    first_job_id VARCHAR NOT NULL)""")
                gold.execute(f"""CREATE TABLE IF NOT EXISTS {builds} (
                    build_id VARCHAR PRIMARY KEY, input_revision_id VARCHAR NOT NULL,
                    source_assessment_revision_id VARCHAR NOT NULL, store_version VARCHAR NOT NULL,
                    feature_version VARCHAR NOT NULL, definition_fingerprint VARCHAR NOT NULL,
                    status VARCHAR NOT NULL, reason_code VARCHAR NOT NULL,
                    source_evidence_fingerprint VARCHAR, result_json VARCHAR NOT NULL,
                    event_ts TIMESTAMPTZ, last_trade_time TIMESTAMPTZ,
                    published_at TIMESTAMPTZ, effective_from TIMESTAMPTZ,
                    effective_to TIMESTAMPTZ, supersedes_json VARCHAR NOT NULL,
                    recorded_at TIMESTAMPTZ NOT NULL, first_job_id VARCHAR NOT NULL)""")
                gold.execute(f"""CREATE TABLE IF NOT EXISTS {attempts} (
                    job_id VARCHAR PRIMARY KEY, build_id VARCHAR NOT NULL,
                    recorded_at TIMESTAMPTZ NOT NULL)""")
                gold.execute("COMMIT")
            except BaseException:
                gold.execute("ROLLBACK")
                raise
        if gold.execute(f"SELECT version FROM {schema_versions} LIMIT 2").fetchall() != [(1,)]:
            raise ValueError("UNSUPPORTED_GOLD_QUOTE_SCHEMA")
        ledger.register_contract(
            DatasetContract(
                name="gold.quote_price_builds",
                version="1",
                layer=Layer.GOLD,
                write_policy=WritePolicy.VERSIONED_BUILDS,
                entity_keys=("build_id",),
                required_columns=("build_id", "event_ts", "published_at", "feature_version"),
                owner="native_gold_quote_features",
            )
        )
        candidate = build_quote_price_candidate(
            bronze,
            frame_silver,
            reference_silver,
            assessments,
            assessment_revision_id=assessment_revision_id,
        )
        payload = asdict(candidate)
        if (
            not _pin(candidate.build_id)
            or _hash(dict(payload, build_id="")) != candidate.build_id
            or candidate.feature_version != FEATURE_VERSION
            or candidate.definition_fingerprint != DEFINITION_FINGERPRINT
            or candidate.source_assessment_revision_id != assessment_revision_id
            or candidate.status not in {"candidate", "blocked"}
            or not re.fullmatch(r"[A-Z0-9_]{1,128}", candidate.reason_code)
            or candidate.canonical_contract_id is not None
            or candidate.published_at is not None
            or candidate.effective_from is not None
            or candidate.effective_to is not None
            or candidate.decision_eligibility_asserted is not False
            or (candidate.status == "blocked" and bool(candidate.features))
            or (
                candidate.status == "candidate"
                and (not candidate.features or not _pin(candidate.source_evidence_fingerprint))
            )
        ):
            raise ValueError("GOLD_CANDIDATE_CONTRACT_MISMATCH")
        encoded = _canonical(payload)
        if len(encoded.encode()) > MAX_RESULT_BYTES:
            raise ValueError("GOLD_CANDIDATE_RESULT_LIMIT")
        event_time = _time(candidate.event_ts)
        trade_time = _time(candidate.last_trade_time)
        gold.execute("BEGIN TRANSACTION")
        try:
            definition = gold.execute(
                f"SELECT definition_fingerprint,CASE WHEN octet_length(encode(definition_json))"
                f"<=32768 THEN definition_json ELSE NULL END FROM {definitions} "
                "WHERE feature_version=?",
                [FEATURE_VERSION],
            ).fetchone()
            if definition is None:
                gold.execute(
                    f"INSERT INTO {definitions} VALUES (?,?,?,?,?)",
                    [
                        FEATURE_VERSION,
                        DEFINITION_FINGERPRINT,
                        definition_json,
                        datetime.now(UTC),
                        job,
                    ],
                )
            elif definition != (DEFINITION_FINGERPRINT, definition_json):
                raise ValueError("FEATURE_DEFINITION_VERSION_CONTENT_MISMATCH")
            expected = (
                input_id,
                assessment_revision_id,
                STORE_VERSION,
                FEATURE_VERSION,
                DEFINITION_FINGERPRINT,
                candidate.status,
                candidate.reason_code,
                candidate.source_evidence_fingerprint,
                encoded,
                event_time,
                trade_time,
                None,
                None,
                None,
            )
            previous = gold.execute(
                f"SELECT input_revision_id,source_assessment_revision_id,store_version,"
                f"feature_version,definition_fingerprint,status,reason_code,"
                f"source_evidence_fingerprint,CASE WHEN octet_length(encode(result_json))<=? "
                f"THEN result_json ELSE NULL END,event_ts,last_trade_time,published_at,"
                f"effective_from,effective_to FROM {builds} WHERE build_id=?",
                [MAX_RESULT_BYTES, candidate.build_id],
            ).fetchone()
            inserted = previous is None
            if previous is not None:
                if previous != expected:
                    raise ValueError("GOLD_BUILD_VERSION_CONTENT_MISMATCH")
            else:
                history = gold.execute(
                    f"SELECT build_id FROM {builds} WHERE input_revision_id=? "
                    "ORDER BY build_id LIMIT ?",
                    [input_id, MAX_HISTORY + 1],
                ).fetchall()
                if len(history) > MAX_HISTORY:
                    raise ValueError("GOLD_BUILD_HISTORY_LIMIT")
                gold.execute(
                    f"INSERT INTO {builds} VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [
                        candidate.build_id,
                        *expected,
                        _canonical([row[0] for row in history]),
                        datetime.now(UTC),
                        job,
                    ],
                )
            gold.execute(
                f"INSERT INTO {attempts} VALUES (?,?,?)",
                [
                    job,
                    candidate.build_id,
                    datetime.now(UTC),
                ],
            )
            gold.execute("COMMIT")
        except BaseException:
            gold.execute("ROLLBACK")
            raise
    return {
        "build_id": candidate.build_id,
        "input_revision_id": input_id,
        "job_id": job,
        "inserted": inserted,
        "status": candidate.status,
        "reason_code": candidate.reason_code,
        "feature_version": FEATURE_VERSION,
        "published": False,
        "decision_eligibility_asserted": False,
    }
