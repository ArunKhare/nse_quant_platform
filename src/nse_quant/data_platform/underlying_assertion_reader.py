"""Archived native recording verification, not current support or verified underlying identity."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from nse_quant.data_platform.underlying_assertion_history import (
    AssertionReviewRequired,
    canonical,
    history_last,
    instant,
    lifecycle,
)

VERSION = "underlying-assertion-recording-consumer@1"
MAX_DOCUMENT_BYTES = 8388608
COLUMNS: dict[tuple[str, str], tuple[str, ...]] = {
    ("identity_evidence", "schema_versions"): ("version",),
    ("identity_evidence", "contracts"): (
        "version",
        "fingerprint",
        "content_json",
        "first_job_id",
    ),
    ("identity_evidence", "definitions"): (
        "version",
        "fingerprint",
        "content_json",
        "first_job_id",
    ),
    ("identity_evidence", "assertions"): (
        "assertion_id",
        "subject_scope_id",
        "store_version",
        "assertion_kind",
        "byte_count",
        "assertion_bytes",
        "prior_assertion_ids_json",
        "recorded_at",
        "first_job_id",
    ),
    ("identity_evidence", "attempts"): ("job_id", "assertion_id", "recorded_at"),
    ("medallion_audit", "schema_versions"): ("version", "applied_at"),
    ("medallion_audit", "dataset_contracts"): (
        "dataset_name",
        "contract_version",
        "fingerprint",
        "contract_json",
        "registered_at",
    ),
    ("medallion_audit", "jobs"): (
        "job_id",
        "parent_job_id",
        "command_name",
        "actor_id",
        "scope_ref",
        "code_revision",
        "config_hash",
        "created_at",
    ),
    ("medallion_audit", "job_events"): (
        "job_id",
        "event_index",
        "state",
        "recorded_at",
        "reason_code",
    ),
}
LIMITS = {name: 2000 for name in COLUMNS}
LIMITS[("identity_evidence", "assertions")] = 1001
LIMITS[("medallion_audit", "job_events")] = 6000


def _quote(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def snapshot(registry: Any) -> dict[tuple[str, str], list[tuple[Any, ...]]]:
    """One entire dedicated native registry table-row observation, no status filters.

    Bounded generic read; validation below interprets schema/contracts/recording.
    File pages, external Bronze, permissions and full DDL are not part of this read.
    """
    current = registry.execute("SELECT current_database()").fetchone()
    if current is None or not any(
        row[1] == current[0] and row[2]
        for row in registry.execute("PRAGMA database_list").fetchall()
    ):
        raise AssertionReviewRequired("FILE_BACKED_ASSERTION_REGISTRY_REQUIRED")
    result: dict[tuple[str, str], list[tuple[Any, ...]]] = {}
    materialized_bytes = 0
    registry.execute("BEGIN TRANSACTION")
    try:
        inventory = registry.execute(
            "SELECT table_schema,table_name,table_type FROM information_schema.tables "
            "WHERE table_catalog=current_database() ORDER BY table_schema,table_name LIMIT 10"
        ).fetchall()
        if inventory != [(s, t, "BASE TABLE") for s, t in sorted(COLUMNS)]:
            raise AssertionReviewRequired("ASSERTION_REGISTRY_INVENTORY_NOT_SUPPORTED")
        for key, expected in sorted(COLUMNS.items()):
            schema, table = key
            columns = registry.execute(
                "SELECT column_name,data_type FROM information_schema.columns "
                "WHERE table_catalog=current_database() AND table_schema=? AND table_name=? "
                "ORDER BY ordinal_position LIMIT 65",
                [schema, table],
            ).fetchall()
            if tuple(c[0] for c in columns) != expected or any(
                kind not in {"VARCHAR", "BLOB", "INTEGER", "BIGINT", "TIMESTAMP WITH TIME ZONE"}
                for _, kind in columns
            ):
                raise AssertionReviewRequired("ASSERTION_REGISTRY_COLUMN_SHAPE_NOT_SUPPORTED")
            qualified = ".".join(map(_quote, (current[0], schema, table)))
            projection: list[str] = []
            guards: list[str] = []
            for column, kind in columns:
                name = _quote(column)
                if kind in {"VARCHAR", "BLOB"}:
                    cap = (
                        70000
                        if column == "prior_assertion_ids_json"
                        else 32768
                        if column in {"content_json", "contract_json"}
                        else 4096
                    )
                    length = (
                        f"octet_length(encode({name}))"
                        if kind == "VARCHAR"
                        else (f"octet_length({name})")
                    )
                    if kind == "BLOB":
                        if (
                            key != ("identity_evidence", "assertions")
                            or column != "assertion_bytes"
                        ):
                            raise AssertionReviewRequired("ASSERTION_UNSUPPORTED_BLOB_COLUMN")
                        cap = 16384
                    guard = f"({name} IS NULL OR {length}<={cap})"
                    projection.append(f"CASE WHEN {guard} THEN {name} END")
                    guards.append(guard)
                else:
                    projection.append(name)
            validity = " AND ".join(guards) or "TRUE"
            rows = registry.execute(
                f"SELECT {','.join(projection)},({validity}) FROM {qualified} LIMIT ?",
                [LIMITS[key] + 1],
            ).fetchall()
            if len(rows) > LIMITS[key] or any(row[-1] is not True for row in rows):
                raise AssertionReviewRequired("ASSERTION_REGISTRY_READ_BOUND_REVIEW_REQUIRED")
            values = [tuple(row[:-1]) for row in rows]
            for row in values:
                for value in row:
                    if isinstance(value, (bytes, str)):
                        size = len(value.encode() if isinstance(value, str) else value)
                        materialized_bytes += size
            if materialized_bytes > MAX_DOCUMENT_BYTES:
                raise AssertionReviewRequired("ASSERTION_REGISTRY_TOTAL_BYTE_LIMIT")
            result[key] = values
        registry.execute("COMMIT")
    except BaseException:
        registry.execute("ROLLBACK")
        raise
    return result


@dataclass(frozen=True)
class UnderlyingAssertionRecording:
    version: str
    assertion_id: str
    status: str
    reason_codes: tuple[str, ...]
    archived_integrity_verified: bool = False
    native_recording_provenance_verified: bool = False
    registry_history_verified: bool = False
    pinned_is_last_distinct_statement: bool = False
    last_distinct_statement_id: str | None = None
    archived_assertion_kind: str | None = None
    audit_obligation_job_ids: tuple[str, ...] = ()
    evidence_fingerprint: str | None = None
    current_bronze_support_checked: bool = False
    bronze_acquisition_provenance_verified: bool = False
    canonical_underlying_id: None = None
    identity_verified: bool = False
    issuer_authenticated: bool = False
    historical_validity_asserted: bool = False
    availability_evidence_verified: bool = False
    decision_eligibility_asserted: bool = False


def read_underlying_assertion_recording(
    registry: Any,
    *,
    assertion_id: str,
) -> UnderlyingAssertionRecording:
    """Archived registry only; no outer transaction, Bronze lookup or audit repair.

    Whole-registry conservative coverage includes other scopes and unlinked failures.
    Prior links mean recorded evidence order, NOT revocation/permission/identity.
    SQL errors propagate. Validation failures require review, not business rejection.
    """
    from nse_quant.data_platform import underlying_assertion as kernel
    from nse_quant.data_platform import underlying_assertion_store as store

    if not kernel.pin(assertion_id):
        raise ValueError("EXACT_UNDERLYING_ASSERTION_PIN_REQUIRED")
    integrity = provenance = history = is_last = False
    kind = last = fingerprint = None
    obligations: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    try:
        data = snapshot(registry)
        if data[("identity_evidence", "schema_versions")] != [(1,)] or [
            row[0] for row in data[("medallion_audit", "schema_versions")]
        ] != [1]:
            raise AssertionReviewRequired("ASSERTION_REGISTRY_SCHEMA_VERSION_NOT_SUPPORTED")
        instant(data[("medallion_audit", "schema_versions")][0][1])
        if store.VERSION != "underlying-assertion-store@1" or kernel.VERSION != (
            "underlying-identity-assertion@1"
        ):
            raise AssertionReviewRequired("ASSERTION_READER_DEPENDENCY_VERSION_NOT_SUPPORTED")
        if (
            kernel.digest(store.CONTRACT) != store.CONTRACT_FINGERPRINT
            or kernel.digest(kernel.DEFINITION) != kernel.DEFINITION_FINGERPRINT
        ):
            raise AssertionReviewRequired("ASSERTION_LOCAL_DEFINITION_FINGERPRINT_MISMATCH")
        rows = data[("identity_evidence", "assertions")]
        by_id = {row[0]: row for row in rows}
        if len(by_id) != len(rows) or assertion_id not in by_id:
            raise AssertionReviewRequired("ASSERTION_NOT_FOUND_OR_DUPLICATED")

        def decode(row: tuple[Any, ...]) -> kernel.UnderlyingAssertion:
            if not kernel.pin(row[0]) or not isinstance(row[5], bytes):
                raise AssertionReviewRequired("ASSERTION_ARCHIVE_ID_OR_BYTES_INVALID")
            try:
                value = kernel.decode_underlying_assertion(row[5], expected_assertion_id=row[0])
                request = kernel.strict_json(value.request_json)
            except (ValueError, TypeError, UnicodeError, RecursionError, KeyError):
                raise AssertionReviewRequired("ASSERTION_ARCHIVE_CONTENT_NOT_VERIFIED") from None
            if (
                kernel.canonical(row[1:5])
                != kernel.canonical(
                    (value.subject_scope_id, store.VERSION, request["assertion"], len(row[5]))
                )
                or not isinstance(row[8], str)
                or not row[8].strip()
            ):
                raise AssertionReviewRequired("ASSERTION_ARCHIVE_METADATA_MISMATCH")
            instant(row[7])
            return value

        target = decode(by_id[assertion_id])
        integrity, kind = True, by_id[assertion_id][3]
        decoded = {pin: decode(row) for pin, row in by_id.items()}
        graphs: dict[str, dict[str, tuple[str, ...]]] = {}
        for pin, row in by_id.items():
            try:
                edges = kernel.strict_json(row[6])
            except (ValueError, TypeError, RecursionError):
                raise AssertionReviewRequired("ASSERTION_PRIOR_EVIDENCE_JSON_INVALID") from None
            if (
                not isinstance(edges, list)
                or len(edges) > store.MAX_HISTORY
                or any(not kernel.pin(x) for x in edges)
                or edges != sorted(set(edges))
                or kernel.canonical(edges) != row[6]
            ):
                raise AssertionReviewRequired("ASSERTION_PRIOR_EVIDENCE_LINKS_INVALID")
            graphs.setdefault(decoded[pin].subject_scope_id, {})[pin] = tuple(edges)
        last_by_scope = {scope: history_last(graph) for scope, graph in graphs.items()}
        jobs_rows = data[("medallion_audit", "jobs")]
        jobs = {row[0]: row for row in jobs_rows}
        if len(jobs) != len(jobs_rows):
            raise AssertionReviewRequired("ASSERTION_DUPLICATE_AUDIT_JOBS")
        event_groups: dict[str, list[tuple[Any, ...]]] = {}
        for event in data[("medallion_audit", "job_events")]:
            if event[0] not in jobs:
                raise AssertionReviewRequired("ASSERTION_ORPHAN_AUDIT_EVENTS")
            event_groups.setdefault(event[0], []).append(event[1:])
        states: dict[str, str] = {}
        config = kernel.digest(
            [store.VERSION, store.CONTRACT_FINGERPRINT, kernel.DEFINITION_FINGERPRINT]
        )
        for job_id, job in jobs.items():
            if (
                not isinstance(job_id, str)
                or not job_id.strip()
                or len(job_id) > 128
                or job[1] is not None
                or job[2] != store.COMMAND
                or job[6] != config
                or not isinstance(job[4], str)
                or not job[4].startswith("sha256:")
                or not kernel.pin(job[4][7:])
                or any(not isinstance(x, str) or not x.strip() for x in (job[3], job[5]))
            ):
                raise AssertionReviewRequired("ASSERTION_AUDIT_JOB_IDENTITY_MISMATCH")
            instant(job[7])
            states[job_id] = lifecycle(sorted(event_groups.get(job_id, []), key=lambda r: r[0]))
        attempts: dict[str, str] = {}
        for job_id, pin, clock in data[("identity_evidence", "attempts")]:
            if job_id in attempts or pin not in decoded or job_id not in jobs:
                raise AssertionReviewRequired("ASSERTION_ATTEMPT_LINK_INVALID")
            if jobs[job_id][4] != "sha256:" + decoded[pin].subject_scope_id:
                raise AssertionReviewRequired("ASSERTION_ATTEMPT_SCOPE_MISMATCH")
            instant(clock)
            attempts[job_id] = pin

        obligations = tuple(
            sorted(job for job in jobs if states[job] != "SUCCEEDED" or job not in attempts)
        )

        def origin(job_id: str, expected_pin: str | None = None) -> None:
            pin = attempts.get(job_id)
            if (
                pin is None
                or (expected_pin is not None and pin != expected_pin)
                or by_id[pin][8] != job_id
                or states.get(job_id) != "SUCCEEDED"
            ):
                raise AssertionReviewRequired("ASSERTION_ORIGIN_NOT_SUCCESSFUL")

        for registry_name, version, fp, content in (
            (
                "contracts",
                store.VERSION,
                store.CONTRACT_FINGERPRINT,
                kernel.canonical(store.CONTRACT),
            ),
            (
                "definitions",
                kernel.VERSION,
                kernel.DEFINITION_FINGERPRINT,
                kernel.canonical(kernel.DEFINITION),
            ),
        ):
            registry_rows = data[("identity_evidence", registry_name)]
            if len(registry_rows) != 1 or registry_rows[0][:3] != (version, fp, content):
                raise AssertionReviewRequired("ASSERTION_REGISTRY_CONTRACT_OR_DEFINITION_MISMATCH")
            origin(registry_rows[0][3])
        if data[("medallion_audit", "dataset_contracts")]:
            raise AssertionReviewRequired("ASSERTION_UNEXPECTED_MEDALLION_CONTRACT_ROWS")
        origin(by_id[assertion_id][8], assertion_id)
        provenance = True
        for pin, row in by_id.items():
            origin(row[8], pin)
        if obligations:
            raise AssertionReviewRequired("ASSERTION_AUDIT_OBLIGATIONS_REQUIRE_REVIEW")
        last = last_by_scope[target.subject_scope_id]

        def projection(value: object) -> object:
            if isinstance(value, bytes):
                return {"sha256": hashlib.sha256(value).hexdigest(), "bytes": len(value)}
            return value

        evidence = [
            [list(key), sorted(canonical([projection(v) for v in row]) for row in values)]
            for key, values in sorted(data.items())
        ]
        raw_fingerprint = canonical([VERSION, assertion_id, evidence]).encode()
        if len(raw_fingerprint) > MAX_DOCUMENT_BYTES:
            raise AssertionReviewRequired("ASSERTION_FINGERPRINT_DOCUMENT_BYTE_LIMIT")
        fingerprint = hashlib.sha256(raw_fingerprint).hexdigest()
        history, is_last = True, assertion_id == last
        reasons = ("ARCHIVED_UNVERIFIED_ASSERTION_RECORDING_VERIFIED",)
    except AssertionReviewRequired as error:
        reasons = (str(error),)
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError):
        reasons = ("ASSERTION_RECORDING_CONTENT_NOT_VERIFIED",)
    return UnderlyingAssertionRecording(
        VERSION,
        assertion_id,
        "verified_archived_recording" if history else "review_required",
        reasons,
        integrity,
        provenance,
        history,
        is_last,
        last,
        kind,
        obligations,
        fingerprint,
    )
