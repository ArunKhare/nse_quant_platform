"""Audited first-write capture of actual migrated-publication research admission."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from nse_quant.data_platform import legacy_market_publication as publication
from nse_quant.data_platform import legacy_market_publication_admission as policy
from nse_quant.data_platform.admission_capture_reader import _lifecycle
from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.publication_admission import (
    AdmissionRequest,
    _request_dict,
    _request_from_json,
)

VERSION = "legacy-research-admission-capture@1"
COMMAND = "capture.legacy_research_admission@1"
MAX_RECEIPT_BYTES = 32768
MAX_REQUEST_BYTES = 512
MAX_REASON_BYTES = 4096
DOMAIN = ("legacy_admission_versions", "legacy_admission_captures", "legacy_admission_attempts")
TABLES = {("decision_inputs", n) for n in DOMAIN} | {
    ("medallion_audit", n) for n in ("schema_versions", "dataset_contracts", "jobs", "job_events")
}
CONTRACT = (
    "decision_inputs.legacy_admission_captures",
    "1",
    "immutable_first_write_request_capture",
    "actual pinned publication assessment; accepted research and rejected policy outcomes",
    "full frozen-summary receipt, not complete publication manifest or independent authority",
    "original audit/link obligations cannot be healed by new recording or execution pins",
)
name = publication.name


@dataclass(frozen=True)
class LegacyAdmissionPins:
    publication_id: str
    recording_fingerprint: str

    def __post_init__(self) -> None:
        if not all(
            publication.bundle.gold.pin(p)
            for p in (self.publication_id, self.recording_fingerprint)
        ):
            raise ValueError("EXACT_CAPTURE_PUBLICATION_PINS_REQUIRED")

    def arguments(self) -> dict[str, str]:
        return dict(
            publication_id=self.publication_id,
            expected_recording_fingerprint=self.recording_fingerprint,
        )


def checked_request(request: AdmissionRequest) -> AdmissionRequest:
    if type(request) is not AdmissionRequest:
        raise TypeError("TYPED_CAPTURE_ADMISSION_REQUEST_REQUIRED")
    return AdmissionRequest(request.use_case, request.knowledge_cutoff, request.economic_at)


def scope_id(publication_id: str, request: AdmissionRequest) -> str:
    if not publication.bundle.gold.pin(publication_id):
        raise ValueError("EXACT_CAPTURE_PUBLICATION_ID_REQUIRED")
    return publication._hash([VERSION, publication_id, _request_dict(checked_request(request))])


def _definition() -> bytes:
    return publication.bundle.gold.canonical(
        [
            VERSION,
            COMMAND,
            CONTRACT,
            policy.VERSION,
            policy.DEFINITION,
            publication.VERSION,
            MAX_RECEIPT_BYTES,
            MAX_REQUEST_BYTES,
            MAX_REASON_BYTES,
        ]
    )


def _config(pins: LegacyAdmissionPins, request: AdmissionRequest) -> str:
    return publication._hash([_definition().hex(), asdict(pins), _request_dict(request)])


def _capture_id(scope: str, pins: LegacyAdmissionPins, receipt_id: str) -> str:
    return publication._hash([VERSION, scope, asdict(pins), receipt_id])


def _owned(conn: Any, *, complete: bool) -> None:
    paths = conn.execute(
        "SELECT path FROM duckdb_databases() WHERE database_name=current_database()"
    ).fetchall()
    if len(paths) != 1 or not paths[0][0]:
        raise ValueError("FILE_BACKED_LEGACY_ADMISSION_CAPTURE_REQUIRED")
    rows = conn.execute(
        "SELECT table_schema,table_name,table_type FROM information_schema.tables "
        "WHERE table_catalog=current_database() ORDER BY table_schema,table_name LIMIT 8"
    ).fetchall()
    known = {(s, t) for s, t, _ in rows}
    if (
        known - TABLES
        or any(kind != "BASE TABLE" for _, _, kind in rows)
        or complete
        and known != TABLES
    ):
        raise ValueError("DEDICATED_LEGACY_ADMISSION_CAPTURE_REQUIRED")


def initialize_legacy_admission_capture(conn: Any) -> None:
    """Explicit empty dedicated target. No adoption or implicit reader initialization."""
    _owned(conn, complete=False)
    if conn.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_catalog=current_database() LIMIT 1"
    ).fetchone():
        raise ValueError("EMPTY_LEGACY_ADMISSION_CAPTURE_REQUIRED")
    AuditLedger(conn).initialize()
    versions, records, attempts = (name(conn, "decision_inputs", n) for n in DOMAIN)
    conn.execute("BEGIN TRANSACTION")
    try:
        conn.execute(f"CREATE SCHEMA {versions.rsplit('.', 1)[0]}")
        conn.execute(f"CREATE TABLE {versions} (version INTEGER PRIMARY KEY,definition BLOB)")
        conn.execute(f"INSERT INTO {versions} VALUES (1,?)", [_definition()])
        conn.execute(f"""CREATE TABLE {records} (
            capture_id VARCHAR PRIMARY KEY,scope_id VARCHAR UNIQUE NOT NULL,
            publication_id VARCHAR NOT NULL,publication_recording_fingerprint VARCHAR NOT NULL,
            request_bytes BLOB NOT NULL,receipt_id VARCHAR NOT NULL,receipt_bytes BLOB NOT NULL,
            receipt_byte_count INTEGER NOT NULL,status VARCHAR NOT NULL,
            reason_codes_bytes BLOB NOT NULL,research_analysis_permitted BOOLEAN NOT NULL,
            decision_eligibility_asserted BOOLEAN NOT NULL,first_job_id VARCHAR NOT NULL,
            recorded_at TIMESTAMPTZ NOT NULL)""")
        conn.execute(f"""CREATE TABLE {attempts} (
            job_id VARCHAR PRIMARY KEY,scope_id VARCHAR NOT NULL,capture_id VARCHAR NOT NULL)""")
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def _schema(conn: Any) -> None:
    _owned(conn, complete=True)
    if policy.VERSION != "legacy-price-research-admission@1":
        raise ValueError("UNSUPPORTED_LEGACY_CAPTURE_POLICY")
    versions = name(conn, "decision_inputs", DOMAIN[0])
    audit = name(conn, "medallion_audit", "schema_versions")
    if conn.execute(
        f"SELECT version,CASE WHEN octet_length(definition)<=32768 THEN definition END "
        f"FROM {versions} LIMIT 2"
    ).fetchall() != [(1, _definition())]:
        raise ValueError("LEGACY_CAPTURE_DEFINITION_OR_CONTRACT_DRIFT")
    if conn.execute(f"SELECT version FROM {audit} LIMIT 2").fetchall() != [(1,)]:
        raise ValueError("LEGACY_CAPTURE_AUDIT_SCHEMA_DRIFT")


def _observe(publications: Any, pins: LegacyAdmissionPins, request: AdmissionRequest) -> bytes:
    result = policy.assess_legacy_publication_use(publications, **pins.arguments(), request=request)
    raw = policy.encode_legacy_admission(result)
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_RECEIPT_BYTES:
        raise ValueError("LEGACY_CAPTURE_OBSERVED_RECEIPT_BYTE_BOUND")
    replayed = policy.replay_legacy_admission(raw, expected_receipt_id=result.receipt_id)
    frozen = json.loads(replayed.frozen_input_json)
    if (
        frozen["source"]["publication_id"] != pins.publication_id
        or frozen["source"]["recording_fingerprint"] != pins.recording_fingerprint
        or frozen["request"] != _request_dict(request)
    ):
        raise ValueError("LEGACY_CAPTURE_ASSESSMENT_SOURCE_OR_REQUEST_MISMATCH")
    return raw


def _unused(conn: Any, scope: str) -> None:
    for table in DOMAIN[1:]:
        if conn.execute(
            f"SELECT 1 FROM {name(conn, 'decision_inputs', table)} WHERE scope_id=? LIMIT 1",
            [scope],
        ).fetchone():
            raise ValueError("LEGACY_CAPTURE_FIRST_WRITE_OR_ORPHAN_OBLIGATION")
    if conn.execute(
        f"SELECT 1 FROM {name(conn, 'medallion_audit', 'jobs')} WHERE scope_ref=? LIMIT 1",
        ["sha256:" + scope],
    ).fetchone():
        raise ValueError("LEGACY_CAPTURE_FIRST_WRITE_ORIGINAL_AUDIT_OBLIGATION")


def capture_legacy_publication_use(
    publications: Any,
    target: Any,
    *,
    pins: LegacyAdmissionPins,
    request: AdmissionRequest,
    actor_id: str,
    code_revision: str,
) -> dict[str, Any]:
    """Actual fresh policy twice; a rejected policy is a valid captured outcome.

    Sources are read-only; target is separate/initialized/single-owner, no outer transaction.
    Domain capture/attempt commit is atomic; final audit is deliberately separate.
    """
    if type(pins) is not LegacyAdmissionPins:
        raise TypeError("TYPED_LEGACY_CAPTURE_PINS_REQUIRED")
    pins = LegacyAdmissionPins(**asdict(pins))
    request = checked_request(request)
    if (
        not publication._identifier(actor_id)
        or type(code_revision) is not str
        or re.fullmatch(r"[a-f0-9]{40}", code_revision) is None
    ):
        raise ValueError("EXPLICIT_LEGACY_CAPTURE_EXECUTION_IDENTIFIERS_REQUIRED")
    publication.foundation._separate(publications, target)
    _schema(target)
    scope = scope_id(pins.publication_id, request)
    _unused(target, scope)
    request_bytes = publication.bundle.gold.canonical(_request_dict(request))
    if len(request_bytes) > MAX_REQUEST_BYTES:
        raise ValueError("LEGACY_CAPTURE_REQUEST_BYTE_BOUND")
    ledger = AuditLedger(target)
    job = ledger.plan_job(
        command_name=COMMAND,
        actor_id=actor_id,
        code_revision=code_revision,
        scope_ref="sha256:" + scope,
        config_hash=_config(pins, request),
    )
    with ledger.execution(job):
        raw = _observe(publications, pins, request)
        if _observe(publications, pins, request) != raw:
            raise ValueError("LEGACY_CAPTURE_NATIVE_ASSESSMENT_DRIFT")
        receipt = policy.replay_legacy_admission(
            raw, expected_receipt_id=publication.bundle.gold.sha(raw)
        )
        reasons = publication.bundle.gold.canonical(receipt.reason_codes)
        if not 0 < len(reasons) <= MAX_REASON_BYTES:
            raise ValueError("LEGACY_CAPTURE_OBSERVED_REASON_BYTE_BOUND")
        key = _capture_id(scope, pins, receipt.receipt_id)
        at = datetime.now(UTC)
        target.execute("BEGIN TRANSACTION")
        try:
            target.execute(
                f"INSERT INTO {name(target, 'decision_inputs', DOMAIN[1])} "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [
                    key,
                    scope,
                    pins.publication_id,
                    pins.recording_fingerprint,
                    request_bytes,
                    receipt.receipt_id,
                    raw,
                    len(raw),
                    receipt.status,
                    reasons,
                    receipt.research_analysis_permitted,
                    False,
                    job,
                    at,
                ],
            )
            target.execute(
                f"INSERT INTO {name(target, 'decision_inputs', DOMAIN[2])} VALUES (?,?,?)",
                [job, scope, key],
            )
            target.execute("COMMIT")
        except BaseException:
            target.execute("ROLLBACK")
            raise
    result = _recording(target, key)
    return dict(
        capture_id=key,
        recording_fingerprint=result.recording_fingerprint,
        receipt_id=receipt.receipt_id,
        status=receipt.status,
        job_id=job,
        decision_eligibility_asserted=False,
    )


@dataclass(frozen=True)
class LegacyAdmissionCapture:
    capture_id: str
    recording_fingerprint: str
    pins: LegacyAdmissionPins
    request_json: str
    receipt_bytes: bytes
    receipt_id: str
    policy_status: str
    recorded_at: str
    native_capture_recording_verified: bool = True
    current_publication_checked: bool = False
    current_native_upstream_checked: bool = False
    research_analysis_authorized: bool = False
    decision_eligibility_asserted: bool = False
    replay_authenticity_asserted: bool = False


def _recording(conn: Any, key: str) -> LegacyAdmissionCapture:
    if not publication.bundle.gold.pin(key):
        raise ValueError("EXACT_LEGACY_CAPTURE_ID_REQUIRED")
    conn.execute("BEGIN TRANSACTION")
    try:
        _schema(conn)
        table = name(conn, "decision_inputs", DOMAIN[1])
        text = publication._text
        header = conn.execute(
            f"SELECT {text('scope_id', 64)} FROM {table} WHERE capture_id=?",
            [key],
        ).fetchone()
        if header is None or not publication.bundle.gold.pin(header[0]):
            raise ValueError("LEGACY_CAPTURE_MISSING_OR_SCOPE_BOUND")
        scope = header[0]
        budget = conn.execute(
            f"SELECT count(*),coalesce(sum(octet_length(receipt_bytes)),0) FROM {table} "
            "WHERE capture_id=? OR scope_id=?",
            [key, scope],
        ).fetchone()
        if budget is None or budget[0] != 1 or not 1 <= budget[1] <= MAX_RECEIPT_BYTES:
            raise ValueError("LEGACY_CAPTURE_COVERAGE_OR_AGGREGATE_BYTE_BOUND")
        row = conn.execute(
            f"SELECT {text('publication_id', 64)},"
            f"{text('publication_recording_fingerprint', 64)},"
            "CASE WHEN octet_length(request_bytes)<=512 THEN request_bytes END,"
            f"{text('receipt_id', 64)},CASE WHEN octet_length(receipt_bytes)<=32768 "
            "THEN receipt_bytes END,receipt_byte_count,"
            f"{text('status', 64)},CASE WHEN octet_length(reason_codes_bytes)<=4096 "
            "THEN reason_codes_bytes END,research_analysis_permitted,"
            f"decision_eligibility_asserted,{text('first_job_id')},recorded_at "
            f"FROM {table} WHERE capture_id=?",
            [key],
        ).fetchone()
        if row is None or any(row[i] is None for i in (0, 1, 2, 3, 4, 6, 7, 10)):
            raise ValueError("LEGACY_CAPTURE_COMPONENT_TRANSFER_BOUND")
        attempts = conn.execute(
            f"SELECT {text('job_id')},{text('scope_id', 64)},{text('capture_id', 64)} "
            f"FROM {name(conn, 'decision_inputs', DOMAIN[2])} "
            "WHERE scope_id=? OR capture_id=? OR job_id=? LIMIT 3",
            [scope, key, row[10]],
        ).fetchall()
        jobs = conn.execute(
            f"SELECT {text('job_id')},{text('parent_job_id')},{text('command_name')},"
            f"{text('actor_id')},{text('scope_ref', 71)},{text('code_revision', 40)},"
            f"{text('config_hash', 64)},created_at "
            f"FROM {name(conn, 'medallion_audit', 'jobs')} "
            "WHERE scope_ref=? OR job_id=? LIMIT 3",
            ["sha256:" + scope, row[10]],
        ).fetchall()
        history = conn.execute(
            "SELECT event_index,CASE WHEN length(state)<=32 THEN state END,recorded_at,"
            "CASE WHEN reason_code IS NULL OR octet_length(encode(reason_code))<=64 "
            "THEN reason_code ELSE 'INVALID!' END "
            f"FROM {name(conn, 'medallion_audit', 'job_events')} "
            "WHERE job_id=? ORDER BY event_index LIMIT 4",
            [row[10]],
        ).fetchall()
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    try:
        pins = LegacyAdmissionPins(row[0], row[1])
        request = _request_from_json(json.loads(bytes(row[2])))
    except (TypeError, ValueError, KeyError, RecursionError):
        raise ValueError("LEGACY_CAPTURE_PINS_OR_REQUEST_MALFORMED") from None
    raw = bytes(row[4])
    receipt = policy.replay_legacy_admission(raw, expected_receipt_id=row[3])
    frozen = json.loads(receipt.frozen_input_json)
    if (
        scope != scope_id(pins.publication_id, request)
        or bytes(row[2]) != publication.bundle.gold.canonical(_request_dict(request))
        or _capture_id(scope, pins, receipt.receipt_id) != key
        or frozen["source"]["publication_id"] != pins.publication_id
        or frozen["source"]["recording_fingerprint"] != pins.recording_fingerprint
        or frozen["request"] != _request_dict(request)
        or row[5:10]
        != (
            len(raw),
            receipt.status,
            publication.bundle.gold.canonical(receipt.reason_codes),
            receipt.research_analysis_permitted,
            False,
        )
    ):
        raise ValueError("LEGACY_CAPTURE_FULL_CONTENT_OR_SCALAR_MISMATCH")
    if attempts != [(row[10], scope, key)] or len(jobs) != 1:
        raise ValueError("LEGACY_CAPTURE_ORIGINAL_LINK_OR_SCOPED_JOB_OBLIGATION")
    job = jobs[0]
    if (
        job[:3] != (row[10], None, COMMAND)
        or not publication._identifier(job[3])
        or job[4] != "sha256:" + scope
        or type(job[5]) is not str
        or re.fullmatch(r"[a-f0-9]{40}", job[5]) is None
        or job[6] != _config(pins, request)
        or _lifecycle(history) != "SUCCEEDED"
    ):
        raise ValueError("LEGACY_CAPTURE_ORIGINAL_AUDIT_NOT_VERIFIED")
    publication._instant(job[7])
    clock = publication._instant(row[11])
    metadata = [
        scope,
        *row[:2],
        bytes(row[2]).hex(),
        row[3],
        publication.bundle.gold.sha(raw),
        *row[5:7],
        bytes(row[7]).hex(),
        *row[8:],
    ]
    fingerprint = publication._hash([VERSION, key, metadata, attempts, jobs, history])
    return LegacyAdmissionCapture(
        key,
        fingerprint,
        pins,
        bytes(row[2]).decode(),
        raw,
        receipt.receipt_id,
        receipt.status,
        clock,
    )


def read_legacy_admission_capture(
    conn: Any,
    *,
    capture_id: str,
    expected_recording_fingerprint: str,
) -> LegacyAdmissionCapture:
    """Pinned original capture and policy replay, NOT current publication/upstream truth."""
    if not publication.bundle.gold.pin(expected_recording_fingerprint):
        raise ValueError("EXACT_LEGACY_CAPTURE_RECORDING_PIN_REQUIRED")
    if conn.execute(
        "SELECT readonly FROM duckdb_databases() WHERE database_name=current_database()"
    ).fetchall() != [(True,)]:
        raise ValueError("READONLY_LEGACY_ADMISSION_CAPTURE_REQUIRED")
    result = _recording(conn, capture_id)
    if result.recording_fingerprint != expected_recording_fingerprint:
        raise ValueError("LEGACY_CAPTURE_RECORDING_FINGERPRINT_CHANGED")
    return result
