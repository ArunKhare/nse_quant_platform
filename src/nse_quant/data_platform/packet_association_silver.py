"""Audited append-only association assessments in a separate dedicated Silver DB."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.contracts import DatasetContract, Layer, WritePolicy
from nse_quant.data_platform.packet_reference_association import (
    ASSOCIATION_VERSION,
    associate_packet_reference,
)

STORE_VERSION = "packet-reference-assessments@1"
COMMAND = "assess.packet_reference@1"
MAX_RESULT_BYTES = 1_048_576
MAX_HISTORY = 1000


def _canonical(value: object) -> str:
    def timestamp(item: object) -> str:
        if not isinstance(item, datetime) or item.tzinfo is None or item.utcoffset() is None:
            raise ValueError("AWARE_TIME_REQUIRED")
        return item.astimezone(UTC).isoformat()

    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=timestamp
    )


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _name(conn: Any, schema: str, table: str) -> str:
    row = conn.execute("SELECT current_database()").fetchone()
    if row is None:
        raise RuntimeError("CATALOG_UNAVAILABLE")
    return ".".join('"' + str(p).replace('"', '""') + '"' for p in (row[0], schema, table))


def _paths(conn: Any) -> set[str]:
    return {str(r[2]) for r in conn.execute("PRAGMA database_list").fetchall() if r[2]}


def persist_packet_association(
    bronze: Any,
    frame_silver: Any,
    reference_silver: Any,
    target: Any,
    *,
    frame_revision_id: str,
    packet_ordinal: int,
    reference_assessment_revision_id: str,
    actor_id: str,
    code_revision: str,
    initialize: bool = False,
) -> dict[str, object]:
    """Reverify inputs per attempt. No arbitrary precomputed-result import API.

    Read connections have no outer transaction; target is single-owner writable.
    Target must be separate from every input. Domain commit and final audit event
    are separate: committed rows/attempt links alone never prove audit success.
    """
    for pin in (frame_revision_id, reference_assessment_revision_id):
        if not isinstance(pin, str) or not re.fullmatch(r"[a-f0-9]{64}", pin):
            raise ValueError("EXACT_FRAME_AND_REFERENCE_PINS_REQUIRED")
    if type(packet_ordinal) is not int or not 0 <= packet_ordinal < 4096:
        raise ValueError("INVALID_PACKET_ORDINAL")
    if not actor_id.strip() or not code_revision.strip():
        raise ValueError("EXECUTION_IDENTITIES_REQUIRED")
    target_paths = _paths(target)
    for source in (bronze, frame_silver, reference_silver):
        if source is target or target_paths & _paths(source):
            raise ValueError("SEPARATE_ASSESSMENT_DATABASE_REQUIRED")
    if target.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_catalog=current_database() "
        "AND table_schema NOT IN ('silver','medallion_audit') LIMIT 1"
    ).fetchone():
        raise ValueError("DEDICATED_SILVER_REQUIRED")
    versions = [STORE_VERSION, ASSOCIATION_VERSION]
    input_id = _digest(
        [frame_revision_id, packet_ordinal, reference_assessment_revision_id, versions]
    )
    ledger = AuditLedger(target)
    if initialize:
        ledger.initialize()
    job = ledger.plan_job(
        command_name=COMMAND,
        actor_id=actor_id,
        scope_ref="sha256:" + input_id,
        code_revision=code_revision,
        config_hash=_digest(versions),
    )
    assessments = _name(target, "silver", "packet_reference_assessments")
    attempts = _name(target, "silver", "packet_reference_attempts")
    schema_table = _name(target, "silver", "packet_reference_schema_versions")
    with ledger.execution(job):
        if initialize:
            target.execute("BEGIN TRANSACTION")
            try:
                target.execute(f"CREATE SCHEMA IF NOT EXISTS {assessments.rsplit('.', 1)[0]}")
                target.execute(
                    f"CREATE TABLE IF NOT EXISTS {schema_table} (version INTEGER PRIMARY KEY)"
                )
                if not target.execute(f"SELECT version FROM {schema_table}").fetchall():
                    target.execute(f"INSERT INTO {schema_table} VALUES (1)")
                target.execute(f"""CREATE TABLE IF NOT EXISTS {assessments} (
                    revision_id VARCHAR PRIMARY KEY, input_revision_id VARCHAR NOT NULL,
                    source_observation_id VARCHAR NOT NULL, packet_ordinal INTEGER NOT NULL,
                    reference_assessment_revision_id VARCHAR NOT NULL,
                    store_version VARCHAR NOT NULL, association_version VARCHAR NOT NULL,
                    status VARCHAR NOT NULL, reason_code VARCHAR NOT NULL,
                    association_fingerprint VARCHAR NOT NULL, result_json VARCHAR NOT NULL,
                    supersedes_json VARCHAR NOT NULL, recorded_at TIMESTAMPTZ NOT NULL,
                    published_at TIMESTAMPTZ, effective_from TIMESTAMPTZ,
                    effective_to TIMESTAMPTZ, first_job_id VARCHAR NOT NULL)""")
                target.execute(f"""CREATE TABLE IF NOT EXISTS {attempts} (
                    job_id VARCHAR PRIMARY KEY, revision_id VARCHAR NOT NULL,
                    recorded_at TIMESTAMPTZ NOT NULL)""")
                target.execute("COMMIT")
            except BaseException:
                target.execute("ROLLBACK")
                raise
        if target.execute(f"SELECT version FROM {schema_table} LIMIT 2").fetchall() != [(1,)]:
            raise ValueError("UNSUPPORTED_ASSOCIATION_STORE_SCHEMA")
        ledger.register_contract(
            DatasetContract(
                name="silver.packet_reference_assessments",
                version="1",
                layer=Layer.SILVER,
                write_policy=WritePolicy.APPEND_REVISIONS,
                entity_keys=("revision_id",),
                required_columns=("revision_id", "source_observation_id", "recorded_at"),
                owner="native_packet_reference",
            )
        )
        result = associate_packet_reference(
            bronze,
            frame_silver,
            reference_silver,
            frame_revision_id=frame_revision_id,
            packet_ordinal=packet_ordinal,
            reference_assessment_revision_id=reference_assessment_revision_id,
        )
        value = asdict(result)
        fingerprint = value["association_fingerprint"]
        unsigned = dict(value, association_fingerprint=None)
        if (
            value["association_version"] != ASSOCIATION_VERSION
            or value["frame_revision_id"] != frame_revision_id
            or value["packet_ordinal"] != packet_ordinal
            or type(value["packet_ordinal"]) is not int
            or value["reference_assessment_revision_id"] != reference_assessment_revision_id
            or value["status"] not in {"associated", "ambiguous", "unresolved", "blocked"}
            or fingerprint != _digest(unsigned)
            or value["canonical_contract_id"] is not None
            or any(
                value[k] is not False
                for k in (
                    "publication_asserted",
                    "historical_validity_asserted",
                    "decision_eligibility_asserted",
                )
            )
        ):
            raise ValueError("ASSOCIATION_RESULT_CONTRACT_MISMATCH")
        encoded = _canonical(value)
        if len(encoded.encode()) > MAX_RESULT_BYTES:
            raise ValueError("ASSOCIATION_RESULT_LIMIT")
        revision = _digest([input_id, fingerprint])
        target.execute("BEGIN TRANSACTION")
        try:
            previous = target.execute(
                f"SELECT input_revision_id,source_observation_id,packet_ordinal,"
                f"reference_assessment_revision_id,store_version,association_version,"
                f"status,reason_code,association_fingerprint,"
                f"CASE WHEN octet_length(encode(result_json))<=? THEN result_json ELSE NULL END "
                f"FROM {assessments} WHERE revision_id=?",
                [MAX_RESULT_BYTES, revision],
            ).fetchone()
            inserted = previous is None
            if previous is not None:
                if previous != (
                    input_id,
                    frame_revision_id,
                    packet_ordinal,
                    reference_assessment_revision_id,
                    *versions,
                    value["status"],
                    value["reason_code"],
                    fingerprint,
                    encoded,
                ):
                    raise ValueError("ASSOCIATION_VERSION_CONTENT_MISMATCH")
            else:
                prior = target.execute(
                    f"SELECT revision_id FROM {assessments} WHERE input_revision_id=? "
                    "ORDER BY revision_id LIMIT ?",
                    [input_id, MAX_HISTORY + 1],
                ).fetchall()
                if len(prior) > MAX_HISTORY:
                    raise ValueError("ASSOCIATION_HISTORY_LIMIT")
                target.execute(
                    f"INSERT INTO {assessments} VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [
                        revision,
                        input_id,
                        frame_revision_id,
                        packet_ordinal,
                        reference_assessment_revision_id,
                        *versions,
                        value["status"],
                        value["reason_code"],
                        fingerprint,
                        encoded,
                        _canonical([r[0] for r in prior]),
                        datetime.now(UTC),
                        None,
                        None,
                        None,
                        job,
                    ],
                )
            target.execute(
                f"INSERT INTO {attempts} VALUES (?,?,?)", [job, revision, datetime.now(UTC)]
            )
            target.execute("COMMIT")
        except BaseException:
            target.execute("ROLLBACK")
            raise
    return {
        "revision_id": revision,
        "input_revision_id": input_id,
        "job_id": job,
        "inserted": inserted,
        "status": value["status"],
        "reason_code": value["reason_code"],
        "published": False,
        "decision_eligibility_asserted": False,
    }
