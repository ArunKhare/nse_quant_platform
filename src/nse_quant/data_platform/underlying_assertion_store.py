"""Audited unverified underlying assertions; supporting source artifacts stay in Bronze."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.underlying_assertion import (
    DEFINITION,
    DEFINITION_FINGERPRINT,
    MAX_ARTIFACT_BYTES,
    MAX_ASSERTION_BYTES,
    UnderlyingAssertionRequest,
    canonical,
    check_supporting_bytes,
    decode_underlying_assertion,
    digest,
    encode_underlying_assertion,
    make_underlying_assertion,
    pin,
    strict_json,
)

VERSION = "underlying-assertion-store@1"
COMMAND = "record.underlying_identity_assertion@1"
MAX_HISTORY = 1000
OWNED = ("schema_versions", "contracts", "definitions", "assertions", "attempts")
CONTRACT = (
    "identity_evidence.assertions@1",
    VERSION,
    "append assertions and attempts atomically; preserve all outcomes and reassessment links",
    "supporting raw source artifacts remain exclusively upstream in Bronze",
    "record/audit completion is not canonical identity, authentication or temporal evidence",
)
CONTRACT_FINGERPRINT = digest(CONTRACT)


def _name(connection: Any, schema: str, table: str) -> str:
    row = connection.execute("SELECT current_database()").fetchone()
    if row is None:
        raise ValueError("ASSERTION_CATALOG_UNAVAILABLE")
    return ".".join('"' + str(x).replace('"', '""') + '"' for x in (row[0], schema, table))


def _paths(connection: Any) -> set[Path]:
    return {
        Path(r[2]).resolve() for r in connection.execute("PRAGMA database_list").fetchall() if r[2]
    }


def _file_backed(connection: Any) -> bool:
    current = connection.execute("SELECT current_database()").fetchone()
    return current is not None and any(
        r[1] == current[0] and r[2] for r in connection.execute("PRAGMA database_list").fetchall()
    )


def _support(bronze: Any, request: UnderlyingAssertionRequest) -> None:
    table = _name(bronze, "bronze", "event_variants")
    variants = bronze.execute(
        f"SELECT CASE WHEN length(envelope_hash)=64 THEN envelope_hash END "
        f"FROM {table} WHERE capture_event_id=? LIMIT 2",
        [request.bronze_capture_event_id],
    ).fetchall()
    if variants != [(request.bronze_envelope_hash,)]:
        raise ValueError("UNDERLYING_SUPPORT_RECEIPT_CONFLICT_OR_MISSING")
    row = bronze.execute(
        f"SELECT CASE WHEN length(payload_hash)=64 THEN payload_hash END,"
        f"CASE WHEN octet_length(payload)<=? THEN payload END,"
        f"CASE WHEN octet_length(encode(envelope_json))<=65536 THEN envelope_json END,"
        f"CASE WHEN octet_length(encode(source))<=4096 THEN source END,"
        f"CASE WHEN octet_length(encode(capture_session_id))<=4096 THEN capture_session_id END,"
        f"CASE WHEN octet_length(encode(source_record_id))<=4096 THEN source_record_id END "
        f"FROM {table} "
        f"WHERE capture_event_id=? AND envelope_hash=?",
        [MAX_ARTIFACT_BYTES, request.bronze_capture_event_id, request.bronze_envelope_hash],
    ).fetchone()
    if row is None or row[1] is None or row[2] is None:
        raise ValueError("UNDERLYING_SUPPORT_MISSING_OR_UNBOUNDED")
    if row[0] != request.evidence_payload_hash or hashlib.sha256(row[2].encode()).hexdigest() != (
        request.bronze_envelope_hash
    ):
        raise ValueError("UNDERLYING_SUPPORT_ENVELOPE_OR_PAYLOAD_PIN_MISMATCH")
    envelope = strict_json(row[2])
    expected_keys = {
        "envelope_version",
        "source",
        "capture_session_id",
        "source_record_id",
        "received_at",
        "payload_hash",
        "payload_format",
        "origin_kind",
        "exchange_ts",
        "provider_event_id",
        "instrument_ref",
    }
    if (
        not isinstance(envelope, dict)
        or set(envelope) != expected_keys
        or type(envelope.get("envelope_version")) is not int
        or envelope["envelope_version"] != 1
        or canonical(envelope) != row[2]
        or any(not isinstance(x, str) or not x for x in row[3:])
        or envelope.get("payload_hash") != request.evidence_payload_hash
        or [envelope.get(k) for k in ("source", "capture_session_id", "source_record_id")]
        != list(row[3:])
        or digest(list(row[3:])) != request.bronze_capture_event_id
    ):
        raise ValueError("UNDERLYING_SUPPORT_ENVELOPE_LINK_MISMATCH")
    check_supporting_bytes(request, bytes(row[1]))


def record_underlying_assertion(
    bronze: Any,
    target: Any,
    *,
    request: UnderlyingAssertionRequest,
    actor_id: str,
    code_revision: str,
    initialize: bool = False,
) -> dict[str, object]:
    """Owned read-only Bronze and separate single-owner writer; no outer transactions.

    Freshly check supporting byte pins, not their meaning/acquisition audits. Never
    import an arbitrary encoded result or upgrade claims into canonical identity.
    Native registry/definition/assertion/attempt domain writes are one transaction.
    Final lifecycle completion is separate and may fail after genuine domain commit.
    """
    assertion = make_underlying_assertion(request)
    raw = encode_underlying_assertion(assertion)
    decode_underlying_assertion(raw, expected_assertion_id=assertion.assertion_id)
    if not actor_id.strip() or not code_revision.strip():
        raise ValueError("ASSERTION_EXECUTION_IDENTITIES_REQUIRED")
    if digest(CONTRACT) != CONTRACT_FINGERPRINT or digest(DEFINITION) != DEFINITION_FINGERPRINT:
        raise ValueError("ASSERTION_CONTRACT_OR_DEFINITION_CHANGED")
    if not _file_backed(bronze) or not _file_backed(target):
        raise ValueError("FILE_BACKED_ASSERTION_DATABASES_REQUIRED")
    if bronze is target or any(
        a == b or (a.exists() and b.exists() and a.samefile(b))
        for a in _paths(bronze)
        for b in _paths(target)
    ):
        raise ValueError("SEPARATE_ASSERTION_DATABASE_REQUIRED")
    inventory = target.execute(
        "SELECT table_schema,table_name FROM information_schema.tables "
        "WHERE table_catalog=current_database() LIMIT 32"
    ).fetchall()
    if len(inventory) == 32 or any(
        s != "medallion_audit" and (s != "identity_evidence" or t not in OWNED)
        for s, t in inventory
    ):
        raise ValueError("DEDICATED_UNDERLYING_ASSERTION_DATABASE_REQUIRED")
    ledger = AuditLedger(target)
    if initialize:
        ledger.initialize()
    job = ledger.plan_job(
        command_name=COMMAND,
        actor_id=actor_id,
        code_revision=code_revision,
        scope_ref="sha256:" + assertion.subject_scope_id,
        config_hash=digest([VERSION, CONTRACT_FINGERPRINT, DEFINITION_FINGERPRINT]),
    )
    tables = {t: _name(target, "identity_evidence", t) for t in OWNED}
    with ledger.execution(job):
        if initialize:
            target.execute("BEGIN TRANSACTION")
            try:
                schema = tables["assertions"].rsplit(".", 1)[0]
                target.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
                target.execute(
                    f"CREATE TABLE IF NOT EXISTS {tables['schema_versions']} "
                    "(version INTEGER PRIMARY KEY)"
                )
                known = target.execute(
                    f"SELECT version FROM {tables['schema_versions']}"
                ).fetchall()
                if known and known != [(1,)]:
                    raise ValueError("UNSUPPORTED_UNDERLYING_ASSERTION_SCHEMA")
                if not known:
                    target.execute(f"INSERT INTO {tables['schema_versions']} VALUES (1)")
                for registry in ("contracts", "definitions"):
                    target.execute(
                        f"CREATE TABLE IF NOT EXISTS {tables[registry]} "
                        "(version VARCHAR PRIMARY KEY,fingerprint VARCHAR NOT NULL,"
                        "content_json VARCHAR NOT NULL,"
                        "first_job_id VARCHAR NOT NULL)"
                    )
                target.execute(
                    f"CREATE TABLE IF NOT EXISTS {tables['assertions']} "
                    "(assertion_id VARCHAR PRIMARY KEY,"
                    "subject_scope_id VARCHAR NOT NULL,"
                    "store_version VARCHAR NOT NULL,assertion_kind VARCHAR NOT NULL,"
                    "byte_count BIGINT NOT NULL,assertion_bytes BLOB NOT NULL,"
                    "prior_assertion_ids_json VARCHAR NOT NULL,"
                    "recorded_at TIMESTAMPTZ NOT NULL,"
                    "first_job_id VARCHAR NOT NULL)"
                )
                target.execute(
                    f"CREATE TABLE IF NOT EXISTS {tables['attempts']} "
                    "(job_id VARCHAR PRIMARY KEY,assertion_id VARCHAR NOT NULL,"
                    "recorded_at TIMESTAMPTZ NOT NULL)"
                )
                target.execute("COMMIT")
            except BaseException:
                target.execute("ROLLBACK")
                raise
        if target.execute(
            f"SELECT version FROM {tables['schema_versions']} LIMIT 2"
        ).fetchall() != [(1,)]:
            raise ValueError("UNSUPPORTED_UNDERLYING_ASSERTION_SCHEMA")
        bronze.execute("BEGIN TRANSACTION")
        try:
            _support(bronze, request)
            bronze.execute("COMMIT")
        except BaseException:
            bronze.execute("ROLLBACK")
            raise
        target.execute("BEGIN TRANSACTION")
        try:
            for registry, version, fingerprint, content in (
                ("contracts", VERSION, CONTRACT_FINGERPRINT, canonical(CONTRACT)),
                ("definitions", assertion.version, DEFINITION_FINGERPRINT, canonical(DEFINITION)),
            ):
                prior_registry = target.execute(
                    f"SELECT CASE WHEN length(fingerprint)=64 THEN fingerprint END,"
                    f"CASE WHEN octet_length(encode(content_json))<=32768 "
                    f"THEN content_json END FROM {tables[registry]} WHERE version=?",
                    [version],
                ).fetchone()
                if prior_registry is None:
                    target.execute(
                        f"INSERT INTO {tables[registry]} VALUES (?,?,?,?)",
                        [version, fingerprint, content, job],
                    )
                elif prior_registry != (fingerprint, content):
                    raise ValueError("UNDERLYING_ASSERTION_REGISTRY_CONTENT_MISMATCH")
            previous = target.execute(
                f"SELECT CASE WHEN length(subject_scope_id)=64 THEN subject_scope_id END,"
                f"CASE WHEN length(store_version)<=128 THEN store_version END,"
                f"CASE WHEN length(assertion_kind)<=16 THEN assertion_kind END,byte_count,"
                f"CASE WHEN octet_length(assertion_bytes)<=? THEN assertion_bytes END "
                f"FROM {tables['assertions']} WHERE assertion_id=?",
                [MAX_ASSERTION_BYTES, assertion.assertion_id],
            ).fetchone()
            expected = (assertion.subject_scope_id, VERSION, request.assertion, len(raw), raw)
            if previous is not None:
                if previous != expected:
                    raise ValueError("UNDERLYING_ASSERTION_STORED_CONTENT_MISMATCH")
            else:
                history = target.execute(
                    f"SELECT CASE WHEN length(assertion_id)=64 THEN assertion_id END "
                    f"FROM {tables['assertions']} WHERE subject_scope_id=? "
                    "ORDER BY assertion_id LIMIT ?",
                    [assertion.subject_scope_id, MAX_HISTORY + 1],
                ).fetchall()
                if any(not pin(r[0]) for r in history):
                    raise ValueError("UNDERLYING_ASSERTION_HISTORY_PINS_INVALID")
                if len(history) > MAX_HISTORY:
                    raise ValueError("UNDERLYING_ASSERTION_HISTORY_LIMIT")
                target.execute(
                    f"INSERT INTO {tables['assertions']} VALUES (?,?,?,?,?,?,?,?,?)",
                    [
                        assertion.assertion_id,
                        *expected,
                        canonical([r[0] for r in history]),
                        datetime.now(UTC),
                        job,
                    ],
                )
            target.execute(
                f"INSERT INTO {tables['attempts']} VALUES (?,?,?)",
                [job, assertion.assertion_id, datetime.now(UTC)],
            )
            target.execute("COMMIT")
        except BaseException:
            target.execute("ROLLBACK")
            raise
    return {
        "execution_status": "COMMITTED_UNVERIFIED_ASSERTION",
        "assertion_id": assertion.assertion_id,
        "subject_scope_id": assertion.subject_scope_id,
        "assertion": request.assertion,
        "job_id": job,
        "inserted": previous is None,
        "canonical_underlying_id": None,
        "identity_verified": False,
        "issuer_authenticated": False,
        "decision_eligibility_asserted": False,
    }
