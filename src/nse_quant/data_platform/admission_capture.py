"""Native audited decision-input receipt capture, not decision execution/admission authority."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.feature_bundle import valid_pin
from nse_quant.data_platform.publication_admission import (
    DEFINITION,
    DEFINITION_FINGERPRINT,
    MAX_RECEIPT_BYTES,
    POLICY_VERSION,
    AdmissionRequest,
    assess_publication_use,
    encode_admission_receipt,
    replay_admission_receipt,
)

STORE_VERSION = "publication-admission-capture@1"
COMMAND = "capture.publication_admission@1"
MAX_HISTORY = 1000
CONTRACT = (
    "decision_inputs.admission_receipts",
    "1",
    "append_immutable_receipts_and_attempts",
    "required:receipt_id,request_revision_id,publication_id,policy_version,definition_fingerprint",
    "required:input_sha256,receipt_bytes,byte_count,status,reason_codes,recorded_at,first_job_id",
    "full frozen input and policy result; request clocks are not source availability/validity",
    "accepted research and rejected outcomes retained; no caller-supplied receipt import",
    "recording/audit success never grant trading, availability, validity or replay authenticity",
)


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


CONTRACT_FINGERPRINT = _hash(CONTRACT)


def _name(conn: Any, table: str) -> str:
    row = conn.execute("SELECT current_database()").fetchone()
    if row is None:
        raise RuntimeError("CATALOG_UNAVAILABLE")
    return ".".join(
        '"' + str(part).replace('"', '""') + '"' for part in (row[0], "decision_inputs", table)
    )


def _paths(conn: Any) -> set[Path]:
    return {
        Path(row[2]).resolve() for row in conn.execute("PRAGMA database_list").fetchall() if row[2]
    }


def _file_backed(conn: Any) -> bool:
    row = conn.execute("SELECT current_database()").fetchone()
    return row is not None and any(
        item[1] == row[0] and item[2] for item in conn.execute("PRAGMA database_list").fetchall()
    )


def _clock(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat() if value is not None else None


def capture_publication_admission(
    publications: Any,
    target: Any,
    *,
    publication_id: str,
    request: AdmissionRequest,
    actor_id: str,
    code_revision: str,
    initialize: bool = False,
) -> dict[str, object]:
    """Read-only publication source; separate single-owner file-backed output.

    Always freshly assess. No arbitrary frozen-receipt import or source backfill.
    Domain receipt/definition/contract/attempt commit is atomic; final audit is not.
    No outer transactions. Policy rejection is a valid persisted domain outcome.
    """
    if not valid_pin(publication_id):
        raise ValueError("EXACT_ADMISSION_PUBLICATION_PIN_REQUIRED")
    if not isinstance(request, AdmissionRequest):
        raise TypeError("TYPED_ADMISSION_REQUEST_REQUIRED")
    checked = AdmissionRequest(request.use_case, request.knowledge_cutoff, request.economic_at)
    if not actor_id.strip() or not code_revision.strip():
        raise ValueError("EXECUTION_IDENTITIES_REQUIRED")
    if POLICY_VERSION != "research-publication-admission@1":
        raise ValueError("UNSUPPORTED_ADMISSION_CAPTURE_POLICY")
    if _hash(DEFINITION) != DEFINITION_FINGERPRINT or _hash(CONTRACT) != CONTRACT_FINGERPRINT:
        raise ValueError("ADMISSION_DEFINITION_OR_CONTRACT_FINGERPRINT_MISMATCH")
    if not _file_backed(publications) or not _file_backed(target):
        raise ValueError("FILE_BACKED_SOURCE_AND_RECEIPT_DATABASES_REQUIRED")
    if publications is target or any(
        a == b or (a.exists() and b.exists() and a.samefile(b))
        for a in _paths(publications)
        for b in _paths(target)
    ):
        raise ValueError("SEPARATE_ADMISSION_RECEIPT_DATABASE_REQUIRED")
    if target.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_catalog=current_database() "
        "AND (table_schema NOT IN ('decision_inputs','medallion_audit') OR "
        "(table_schema='decision_inputs' AND table_name NOT IN ('admission_schema_versions',"
        "'admission_contracts','admission_definitions','admission_receipts',"
        "'admission_attempts'))) "
        "LIMIT 1"
    ).fetchone():
        raise ValueError("DEDICATED_ADMISSION_RECEIPT_DATABASE_REQUIRED")
    request_document = {
        "use_case": checked.use_case,
        "knowledge_cutoff": _clock(checked.knowledge_cutoff),
        "economic_at": _clock(checked.economic_at),
    }
    if max(len(_canonical(DEFINITION).encode()), len(_canonical(CONTRACT).encode())) > 32768:
        raise ValueError("ADMISSION_LOCAL_CONTRACT_BYTE_LIMIT")
    versions = [STORE_VERSION, POLICY_VERSION, DEFINITION_FINGERPRINT, CONTRACT_FINGERPRINT]
    request_revision = _hash([versions, publication_id, request_document])
    ledger = AuditLedger(target)
    if initialize:
        ledger.initialize()
    job = ledger.plan_job(
        command_name=COMMAND,
        actor_id=actor_id,
        scope_ref="sha256:" + request_revision,
        code_revision=code_revision,
        config_hash=_hash(versions),
    )
    schema = _name(target, "admission_schema_versions")
    contracts = _name(target, "admission_contracts")
    definitions = _name(target, "admission_definitions")
    receipts = _name(target, "admission_receipts")
    attempts = _name(target, "admission_attempts")
    with ledger.execution(job):
        if initialize:
            target.execute("BEGIN TRANSACTION")
            try:
                target.execute(f"CREATE SCHEMA IF NOT EXISTS {receipts.rsplit('.', 1)[0]}")
                target.execute(f"CREATE TABLE IF NOT EXISTS {schema} (version INTEGER PRIMARY KEY)")
                known = target.execute(f"SELECT version FROM {schema}").fetchall()
                if known and known != [(1,)]:
                    raise ValueError("UNSUPPORTED_ADMISSION_STORE_SCHEMA")
                if not known:
                    target.execute(f"INSERT INTO {schema} VALUES (1)")
                target.execute(f"""CREATE TABLE IF NOT EXISTS {contracts} (
                    contract_name VARCHAR NOT NULL,contract_version VARCHAR NOT NULL,
                    fingerprint VARCHAR NOT NULL,contract_json VARCHAR NOT NULL,
                    recorded_at TIMESTAMPTZ NOT NULL,first_job_id VARCHAR NOT NULL,
                    PRIMARY KEY(contract_name,contract_version))""")
                target.execute(f"""CREATE TABLE IF NOT EXISTS {definitions} (
                    policy_version VARCHAR PRIMARY KEY,definition_fingerprint VARCHAR NOT NULL,
                    definition_json VARCHAR NOT NULL,recorded_at TIMESTAMPTZ NOT NULL,
                    first_job_id VARCHAR NOT NULL)""")
                target.execute(f"""CREATE TABLE IF NOT EXISTS {receipts} (
                    receipt_id VARCHAR PRIMARY KEY,request_revision_id VARCHAR NOT NULL,
                    store_version VARCHAR NOT NULL,policy_version VARCHAR NOT NULL,
                    definition_fingerprint VARCHAR NOT NULL,publication_id VARCHAR NOT NULL,
                    use_case VARCHAR NOT NULL,request_knowledge_cutoff TIMESTAMPTZ,
                    request_economic_at TIMESTAMPTZ,input_sha256 VARCHAR NOT NULL,
                    source_evidence_fingerprint VARCHAR,bundle_id VARCHAR,status VARCHAR NOT NULL,
                    reason_codes_json VARCHAR NOT NULL,research_analysis_permitted BOOLEAN NOT NULL,
                    decision_eligibility_asserted BOOLEAN NOT NULL,
                    receipt_byte_count BIGINT NOT NULL,
                    receipt_bytes BLOB NOT NULL,supersedes_json VARCHAR NOT NULL,
                    recorded_at TIMESTAMPTZ NOT NULL,first_job_id VARCHAR NOT NULL)""")
                target.execute(f"""CREATE TABLE IF NOT EXISTS {attempts} (
                    job_id VARCHAR PRIMARY KEY,receipt_id VARCHAR NOT NULL,
                    input_sha256 VARCHAR NOT NULL,
                    recorded_at TIMESTAMPTZ NOT NULL)""")
                target.execute("COMMIT")
            except BaseException:
                target.execute("ROLLBACK")
                raise
        if target.execute(f"SELECT version FROM {schema} LIMIT 2").fetchall() != [(1,)]:
            raise ValueError("UNSUPPORTED_ADMISSION_STORE_SCHEMA")
        receipt = assess_publication_use(
            publications, publication_id=publication_id, request=checked
        )
        raw = encode_admission_receipt(receipt)
        replayed = replay_admission_receipt(raw, expected_receipt_id=receipt.receipt_id)
        frozen = json.loads(replayed.frozen_input_json)
        if (
            replayed.publication_id != publication_id
            or replayed.policy_version != POLICY_VERSION
            or replayed.definition_fingerprint != DEFINITION_FINGERPRINT
            or frozen["request"] != request_document
            or replayed.decision_eligibility_asserted is not False
            or replayed.availability_evidence_verified is not False
            or replayed.economic_validity_verified is not False
            or replayed.source_current_checked is not False
            or replayed.replay_authenticity_asserted is not False
        ):
            raise ValueError("CAPTURED_ADMISSION_CONTRACT_MISMATCH")
        if len(raw) > MAX_RECEIPT_BYTES:
            raise ValueError("CAPTURED_ADMISSION_BYTE_LIMIT")
        expected = (
            request_revision,
            STORE_VERSION,
            POLICY_VERSION,
            DEFINITION_FINGERPRINT,
            publication_id,
            checked.use_case,
            checked.knowledge_cutoff.astimezone(UTC) if checked.knowledge_cutoff else None,
            checked.economic_at.astimezone(UTC) if checked.economic_at else None,
            replayed.input_sha256,
            replayed.source_evidence_fingerprint,
            replayed.bundle_id,
            replayed.status,
            _canonical(replayed.reason_codes),
            replayed.research_analysis_permitted,
            False,
            len(raw),
            raw,
        )
        target.execute("BEGIN TRANSACTION")
        try:
            existing_contract = target.execute(
                f"SELECT fingerprint,CASE WHEN octet_length(encode(contract_json))<=32768 "
                f"THEN contract_json ELSE NULL END FROM {contracts} "
                "WHERE contract_name=? AND contract_version='1'",
                [CONTRACT[0]],
            ).fetchone()
            if existing_contract is None:
                target.execute(
                    f"INSERT INTO {contracts} VALUES (?,?,?,?,?,?)",
                    [
                        CONTRACT[0],
                        "1",
                        CONTRACT_FINGERPRINT,
                        _canonical(CONTRACT),
                        datetime.now(UTC),
                        job,
                    ],
                )
            elif existing_contract != (CONTRACT_FINGERPRINT, _canonical(CONTRACT)):
                raise ValueError("ADMISSION_STORE_CONTRACT_VERSION_MISMATCH")
            definition = target.execute(
                f"SELECT definition_fingerprint,CASE WHEN "
                f"octet_length(encode(definition_json))<=32768 "
                f"THEN definition_json ELSE NULL END "
                f"FROM {definitions} WHERE policy_version=?",
                [POLICY_VERSION],
            ).fetchone()
            if definition is None:
                target.execute(
                    f"INSERT INTO {definitions} VALUES (?,?,?,?,?)",
                    [
                        POLICY_VERSION,
                        DEFINITION_FINGERPRINT,
                        _canonical(DEFINITION),
                        datetime.now(UTC),
                        job,
                    ],
                )
            elif definition != (DEFINITION_FINGERPRINT, _canonical(DEFINITION)):
                raise ValueError("ADMISSION_POLICY_VERSION_CONTENT_MISMATCH")
            previous = target.execute(
                f"SELECT request_revision_id,store_version,policy_version,definition_fingerprint,"
                f"publication_id,use_case,request_knowledge_cutoff,request_economic_at,"
                f"input_sha256,"
                f"source_evidence_fingerprint,bundle_id,status,CASE WHEN "
                f"octet_length(encode(reason_codes_json))<=16384 THEN reason_codes_json "
                f"ELSE NULL END,research_analysis_permitted,"
                f"decision_eligibility_asserted,receipt_byte_count,"
                f"CASE WHEN octet_length(receipt_bytes)<=? THEN receipt_bytes ELSE NULL END "
                f"FROM {receipts} WHERE receipt_id=?",
                [MAX_RECEIPT_BYTES, receipt.receipt_id],
            ).fetchone()
            if previous is not None:
                if previous != expected:
                    raise ValueError("ADMISSION_RECEIPT_VERSION_CONTENT_MISMATCH")
            else:
                history = target.execute(
                    f"SELECT receipt_id FROM {receipts} WHERE request_revision_id=? "
                    "ORDER BY receipt_id LIMIT ?",
                    [request_revision, MAX_HISTORY + 1],
                ).fetchall()
                if len(history) > MAX_HISTORY:
                    raise ValueError("ADMISSION_RECEIPT_HISTORY_LIMIT")
                target.execute(
                    f"INSERT INTO {receipts} VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [
                        receipt.receipt_id,
                        *expected,
                        _canonical([row[0] for row in history]),
                        datetime.now(UTC),
                        job,
                    ],
                )
            target.execute(
                f"INSERT INTO {attempts} VALUES (?,?,?,?)",
                [
                    job,
                    receipt.receipt_id,
                    receipt.input_sha256,
                    datetime.now(UTC),
                ],
            )
            target.execute("COMMIT")
        except BaseException:
            target.execute("ROLLBACK")
            raise
    return {
        "receipt_id": receipt.receipt_id,
        "request_revision_id": request_revision,
        "job_id": job,
        "inserted": previous is None,
        "status": receipt.status,
        "research_analysis_permitted": receipt.research_analysis_permitted,
        "decision_eligibility_asserted": False,
        "replay_authenticity_asserted": False,
    }
