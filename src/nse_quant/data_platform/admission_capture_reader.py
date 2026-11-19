"""Bounded archived capture provenance; never current admission or authorization."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from nse_quant.data_platform import admission_capture as store
from nse_quant.data_platform import publication_admission as policy
from nse_quant.data_platform.feature_bundle import valid_pin

READER_VERSION = "publication-admission-capture-consumer@1"
MAX_ROWS = 1001
MAX_JOBS = 2000
MAX_TOTAL_BYTES = 33_554_432


def _name(conn: Any, schema: str, table: str) -> str:
    row = conn.execute("SELECT current_database()").fetchone()
    if row is None:
        raise ValueError("CAPTURE_CATALOG_UNAVAILABLE")
    return ".".join('"' + str(x).replace('"', '""') + '"' for x in (row[0], schema, table))


def _instant(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("CAPTURE_AWARE_CLOCK_REQUIRED")
    return value.astimezone(UTC).isoformat()


def _lifecycle(rows: list[tuple[Any, ...]]) -> str:
    if not 1 <= len(rows) <= 3:
        return "INVALID"
    if [r[0] for r in rows] != list(range(1, len(rows) + 1)):
        return "INVALID"
    for _, _, clock, reason in rows:
        if _instant(clock) is None:
            return "INVALID"
        if reason is not None and not re.fullmatch(r"[A-Z0-9_]{1,64}", reason):
            return "INVALID"
    states = tuple(r[1] for r in rows)
    if states == ("PLANNED", "RUNNING", "SUCCEEDED"):
        return "SUCCEEDED" if all(r[3] is None for r in rows) else "INVALID"
    if states in {("PLANNED",), ("PLANNED", "RUNNING")}:
        return "INCOMPLETE" if all(r[3] is None for r in rows) else "INVALID"
    if states[-1] in {"FAILED", "CANCELLED"} and states[:-1] in {
        ("PLANNED",),
        ("PLANNED", "RUNNING"),
    }:
        return states[-1] if all(r[3] is None for r in rows[:-1]) else "INVALID"
    return "INVALID"


def _head(graph: dict[str, tuple[str, ...]]) -> str:
    """Writer links ALL prior receipts; require a complete comparable DAG."""
    if not graph or any(
        len(set(edges)) != len(edges) or node in edges or set(edges) - graph.keys()
        for node, edges in graph.items()
    ):
        raise ValueError("CAPTURE_HISTORY_GRAPH_INVALID")
    ordered = sorted(graph, key=lambda node: len(graph[node]))
    seen: set[str] = set()
    for node in ordered:
        if set(graph[node]) != seen:
            raise ValueError("CAPTURE_HISTORY_GRAPH_INCOMPLETE_OR_FORKED")
        seen.add(node)
    return ordered[-1]


@dataclass(frozen=True)
class AdmissionCaptureEvidence:
    reader_version: str
    receipt_id: str
    status: str
    reason_codes: tuple[str, ...]
    archived_integrity_verified: bool = False
    native_capture_provenance_verified: bool = False
    reassessment_history_verified: bool = False
    pinned_receipt_is_history_head: bool = False
    archived_policy_status: str | None = None
    history_head_receipt_id: str | None = None
    current_request_checked: bool = False
    research_analysis_authorized: bool = False
    decision_eligibility_asserted: bool = False
    replay_authenticity_asserted: bool = False


def _record(
    conn: Any, receipt_id: str
) -> tuple[policy.AdmissionReceipt, str, str, tuple[str, ...]]:
    table = _name(conn, "decision_inputs", "admission_receipts")
    row = conn.execute(
        f"SELECT request_revision_id,store_version,policy_version,definition_fingerprint,"
        f"publication_id,use_case,request_knowledge_cutoff,request_economic_at,input_sha256,"
        f"source_evidence_fingerprint,bundle_id,status,"
        f"CASE WHEN octet_length(encode(reason_codes_json))<=16384 "
        f"THEN reason_codes_json END,research_analysis_permitted,decision_eligibility_asserted,"
        f"receipt_byte_count,CASE WHEN octet_length(receipt_bytes)<=? THEN receipt_bytes END,"
        f"CASE WHEN octet_length(encode(supersedes_json))<=70000 THEN supersedes_json END,"
        f"recorded_at,first_job_id FROM {table} WHERE receipt_id=?",
        [policy.MAX_RECEIPT_BYTES, receipt_id],
    ).fetchone()
    if row is None or row[16] is None:
        raise ValueError("CAPTURE_RECEIPT_MISSING_OR_UNBOUNDED")
    raw = bytes(row[16])
    receipt = policy.replay_admission_receipt(raw, expected_receipt_id=receipt_id)
    request = json.loads(receipt.frozen_input_json)["request"]
    versions = [
        store.STORE_VERSION,
        policy.POLICY_VERSION,
        policy.DEFINITION_FINGERPRINT,
        store.CONTRACT_FINGERPRINT,
    ]
    revision = store._hash([versions, receipt.publication_id, request])
    expected = (
        revision,
        store.STORE_VERSION,
        policy.POLICY_VERSION,
        policy.DEFINITION_FINGERPRINT,
        receipt.publication_id,
        request["use_case"],
        request["knowledge_cutoff"],
        request["economic_at"],
        receipt.input_sha256,
        receipt.source_evidence_fingerprint,
        receipt.bundle_id,
        receipt.status,
        store._canonical(receipt.reason_codes),
        receipt.research_analysis_permitted,
        False,
        len(raw),
    )
    actual = (*row[:6], _instant(row[6]), _instant(row[7]), *row[8:16])
    if store._canonical(actual) != store._canonical(expected) or _instant(row[18]) is None:
        raise ValueError("CAPTURE_METADATA_MISMATCH")
    links = policy._json(row[17]) if isinstance(row[17], str) else None
    if (
        not isinstance(links, list)
        or len(links) > store.MAX_HISTORY
        or any(not valid_pin(pin) for pin in links)
        or store._canonical(links) != row[17]
        or links != sorted(set(links))
    ):
        raise ValueError("CAPTURE_HISTORY_LINKS_INVALID")
    if not isinstance(row[19], str) or not row[19].strip():
        raise ValueError("CAPTURE_ORIGIN_MISSING")
    return receipt, revision, row[19], tuple(links)


def _job(conn: Any, job: str, revision: str) -> str:
    jobs = _name(conn, "medallion_audit", "jobs")
    events = _name(conn, "medallion_audit", "job_events")
    row = conn.execute(
        f"SELECT command_name,scope_ref,config_hash,"
        f"CASE WHEN length(actor_id)<=4096 THEN actor_id END,"
        f"CASE WHEN length(code_revision)<=4096 THEN code_revision END,created_at "
        f"FROM {jobs} WHERE job_id=?",
        [job],
    ).fetchone()
    versions = [
        store.STORE_VERSION,
        policy.POLICY_VERSION,
        policy.DEFINITION_FINGERPRINT,
        store.CONTRACT_FINGERPRINT,
    ]
    if (
        row is None
        or row[:3] != (store.COMMAND, "sha256:" + revision, store._hash(versions))
        or any(not isinstance(x, str) or not x.strip() for x in row[3:5])
        or _instant(row[5]) is None
    ):
        raise ValueError("CAPTURE_JOB_IDENTITY_MISMATCH")
    lifecycle = conn.execute(
        f"SELECT event_index,CASE WHEN length(state)<=32 THEN state END,recorded_at,"
        f"CASE WHEN reason_code IS NULL OR length(reason_code)<=64 THEN reason_code "
        f"ELSE 'INVALID!' END FROM {events} WHERE job_id=? ORDER BY event_index LIMIT 4",
        [job],
    ).fetchall()
    return _lifecycle(lifecycle)


def read_admission_capture(captures: Any, *, receipt_id: str) -> AdmissionCaptureEvidence:
    """Owned file-backed connection, no outer transaction. SQL failures propagate.

    Use a read_only=True connection. This API issues only SELECT and transaction
    control. Frozen replay, archived provenance and history are independent flags;
    none authorizes use or checks current publication/request admissibility.
    """
    if not valid_pin(receipt_id):
        raise ValueError("EXACT_CAPTURE_RECEIPT_PIN_REQUIRED")
    if not store._file_backed(captures):
        raise ValueError("FILE_BACKED_CAPTURE_DATABASE_REQUIRED")
    integrity = provenance = history = is_head = False
    policy_status = head = None
    reasons: tuple[str, ...] = ()
    captures.execute("BEGIN TRANSACTION")
    try:
        unexpected = captures.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_catalog=current_database() "
            "AND (table_schema NOT IN ('decision_inputs','medallion_audit') OR "
            "(table_schema='decision_inputs' AND table_name NOT IN "
            "('admission_schema_versions','admission_contracts','admission_definitions',"
            "'admission_receipts','admission_attempts'))) LIMIT 1"
        ).fetchone()
        if unexpected is not None:
            raise ValueError("DEDICATED_CAPTURE_DATABASE_NOT_VERIFIED")
        for schema, table in (
            ("decision_inputs", "admission_schema_versions"),
            ("medallion_audit", "schema_versions"),
        ):
            name = _name(captures, schema, table)
            if captures.execute(f"SELECT version FROM {name} LIMIT 2").fetchall() != [(1,)]:
                raise ValueError("UNSUPPORTED_CAPTURE_SCHEMA")
        receipt, revision, origin, _ = _record(captures, receipt_id)
        integrity, policy_status = True, receipt.status
        attempts = _name(captures, "decision_inputs", "admission_attempts")

        def origin_verified(job: str, expected_pin: str | None = None) -> None:
            links = captures.execute(
                f"SELECT receipt_id,input_sha256,recorded_at FROM {attempts} WHERE job_id=?",
                [job],
            ).fetchall()
            if len(links) != 1 or (expected_pin is not None and links[0][0] != expected_pin):
                raise ValueError("CAPTURE_ORIGIN_ATTEMPT_MISSING")
            original, original_revision, first, _ = _record(captures, links[0][0])
            if (
                first != job
                or original.input_sha256 != links[0][1]
                or _instant(links[0][2]) is None
                or _job(captures, job, original_revision) != "SUCCEEDED"
            ):
                raise ValueError("CAPTURE_ORIGIN_NOT_SUCCESSFUL")

        for table, where, params, expected in (
            (
                "admission_contracts",
                "contract_name=? AND contract_version='1'",
                [store.CONTRACT[0]],
                (store.CONTRACT_FINGERPRINT, store._canonical(store.CONTRACT)),
            ),
            (
                "admission_definitions",
                "policy_version=?",
                [policy.POLICY_VERSION],
                (policy.DEFINITION_FINGERPRINT, store._canonical(policy.DEFINITION)),
            ),
        ):
            name = _name(captures, "decision_inputs", table)
            fp, content = (
                ("fingerprint", "contract_json")
                if table == "admission_contracts"
                else ("definition_fingerprint", "definition_json")
            )
            registered = captures.execute(
                f"SELECT {fp},CASE WHEN octet_length(encode({content}))<=32768 "
                f"THEN {content} END,first_job_id,recorded_at FROM {name} WHERE {where}",
                params,
            ).fetchone()
            if registered is None or registered[:2] != expected or _instant(registered[3]) is None:
                raise ValueError("CAPTURE_REGISTRY_CONTENT_MISMATCH")
            origin_verified(registered[2])
        origin_verified(origin, receipt_id)
        provenance = True
        records = _name(captures, "decision_inputs", "admission_receipts")
        nodes = captures.execute(
            f"SELECT receipt_id,octet_length(receipt_bytes) FROM {records} "
            f"WHERE request_revision_id=? ORDER BY receipt_id LIMIT ?",
            [revision, MAX_ROWS + 1],
        ).fetchall()
        if len(nodes) > MAX_ROWS or sum(n[1] for n in nodes) > MAX_TOTAL_BYTES:
            raise ValueError("CAPTURE_HISTORY_BOUND_REVIEW_REQUIRED")
        graph: dict[str, tuple[str, ...]] = {}
        inputs: dict[str, str] = {}
        for pin, _size in nodes:
            item, item_revision, first_job, edges = _record(captures, pin)
            if item_revision != revision:
                raise ValueError("CAPTURE_HISTORY_REQUEST_MISMATCH")
            graph[pin], inputs[pin] = edges, item.input_sha256
            origin_verified(first_job, pin)
        head = _head(graph)
        jobs = _name(captures, "medallion_audit", "jobs")
        scoped = captures.execute(
            f"SELECT j.job_id,a.receipt_id,a.input_sha256,a.recorded_at FROM {jobs} j "
            f"LEFT JOIN {attempts} a ON j.job_id=a.job_id WHERE j.scope_ref=? "
            f"ORDER BY j.job_id LIMIT ?",
            ["sha256:" + revision, MAX_JOBS + 1],
        ).fetchall()
        linked = captures.execute(
            f"SELECT a.job_id FROM {attempts} a JOIN {records} r ON r.receipt_id=a.receipt_id "
            f"WHERE r.request_revision_id=? ORDER BY a.job_id LIMIT ?",
            [revision, MAX_JOBS + 1],
        ).fetchall()
        if (
            not scoped
            or len(scoped) > MAX_JOBS
            or len(linked) > MAX_JOBS
            or {r[0] for r in scoped} != {r[0] for r in linked}
        ):
            raise ValueError("CAPTURE_ATTEMPT_COVERAGE_REVIEW_REQUIRED")
        for job, pin, input_hash, clock in scoped:
            if (
                pin not in inputs
                or inputs[pin] != input_hash
                or _instant(clock) is None
                or _job(captures, job, revision) != "SUCCEEDED"
            ):
                raise ValueError("CAPTURE_ATTEMPT_REVIEW_REQUIRED")
        history, is_head = True, head == receipt_id
        reasons = (
            ("ARCHIVED_CAPTURE_AND_HISTORY_VERIFIED",)
            if is_head
            else ("ARCHIVED_CAPTURE_VERIFIED_BUT_REASSESSED",)
        )
    except ValueError as error:
        # Only service-owned validation codes; SQL/operational failures still raise.
        code = str(error)
        reasons = (
            code if re.fullmatch(r"[A-Z0-9_]{1,128}", code) else "CAPTURE_CONTENT_NOT_VERIFIED",
        )
    except BaseException:
        captures.execute("ROLLBACK")
        raise
    captures.execute("COMMIT")
    return AdmissionCaptureEvidence(
        READER_VERSION,
        receipt_id,
        "verified_archived_capture" if history else "review_required",
        reasons,
        integrity,
        provenance,
        history,
        is_head,
        policy_status,
        head,
    )
