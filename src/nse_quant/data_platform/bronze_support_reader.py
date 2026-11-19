"""Bounded pinned Bronze storage lineage, not source semantics or identity authority."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

VERSION = "pinned-bronze-support-storage@1"
MAX_PAYLOAD_BYTES = 1048576
MAX_BATCH_BYTES = 8388608
MAX_ARTIFACT_BYTES = 16777216
MAX_BATCH_EVENTS = 64
MAX_JOBS = 1000
MAX_EVENTS = 6000
SUCCESS_PATHS = (
    ("PLANNED", "RUNNING", "SUCCEEDED"),
    ("PLANNED", "RUNNING", "STAGED", "VALIDATED", "PUBLISHED", "SUCCEEDED"),
)


class SupportReviewRequired(ValueError):
    """Evidence insufficient for this explicit storage profile, never business rejection."""


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _pin(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _instant(value: object) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise SupportReviewRequired("SUPPORT_AWARE_METADATA_CLOCK_REQUIRED")
    return value.astimezone(UTC).isoformat()


def _canonical(value: object) -> str:
    def encode(item: object) -> object:
        if isinstance(item, bytes):
            return {"sha256": _hash(item), "bytes": len(item)}
        return _instant(item)

    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=encode)


def _json(raw: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise SupportReviewRequired("SUPPORT_DUPLICATE_JSON_KEY")
            result[key] = value
        return result

    def invalid(_value: str) -> Any:
        raise SupportReviewRequired("SUPPORT_NONFINITE_JSON")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def _text(value: object, limit: int) -> bool:
    return isinstance(value, str) and 0 < len(value) <= limit and value == value.strip()


@dataclass(frozen=True)
class BronzeSupportPin:
    capture_event_id: str
    envelope_hash: str
    payload_hash: str
    byte_start: int
    byte_end: int
    fragment_sha256: str

    def __post_init__(self) -> None:
        if not all(
            _pin(value)
            for value in (
                self.capture_event_id,
                self.envelope_hash,
                self.payload_hash,
                self.fragment_sha256,
            )
        ):
            raise ValueError("EXACT_BRONZE_SUPPORT_HASH_PINS_REQUIRED")
        if (
            type(self.byte_start) is not int
            or type(self.byte_end) is not int
            or not 0 <= self.byte_start < self.byte_end <= MAX_PAYLOAD_BYTES
        ):
            raise ValueError("BOUNDED_BRONZE_SUPPORT_BYTE_INTERVAL_REQUIRED")


@dataclass(frozen=True)
class IngestAuditExpectation:
    command_name: str
    scope_ref: str
    config_hash: str

    def __post_init__(self) -> None:
        if (
            not _text(self.command_name, 128)
            or not _text(self.scope_ref, 512)
            or not _pin(self.config_hash)
            or any(ord(c) < 32 for c in self.command_name + self.scope_ref)
        ):
            raise ValueError("EXPLICIT_BOUNDED_INGEST_AUDIT_EXPECTATION_REQUIRED")


@dataclass(frozen=True)
class BronzeSupportEvidence:
    version: str
    capture_event_id: str
    status: str
    reason_codes: tuple[str, ...]
    current_payload_integrity_verified: bool = False
    retained_input_artifact_verified: bool = False
    fresh_batch_membership_verified: bool = False
    origin_ingest_audit_verified: bool = False
    scoped_audit_history_verified: bool = False
    audit_obligation_job_ids: tuple[str, ...] = ()
    evidence_fingerprint: str | None = None
    retry_link_coverage_verified: bool = False
    artifact_to_event_semantics_verified: bool = False
    source_acquisition_authenticity_asserted: bool = False
    identity_verified: bool = False
    issuer_authenticated: bool = False
    availability_evidence_verified: bool = False
    historical_validity_asserted: bool = False
    decision_eligibility_asserted: bool = False


def _name(conn: Any, schema: str, table: str) -> str:
    current = conn.execute("SELECT current_database()").fetchone()
    if current is None:
        raise SupportReviewRequired("SUPPORT_CATALOG_UNAVAILABLE")
    return ".".join('"' + str(x).replace('"', '""') + '"' for x in (current[0], schema, table))


def _select(
    conn: Any,
    table: str,
    columns: tuple[str, ...],
    where: str,
    args: list[object],
    limit: int,
    *,
    order: str = "",
) -> list[tuple[Any, ...]]:
    projection: list[str] = []
    guards: list[str] = []
    blobs = {"payload": MAX_PAYLOAD_BYTES, "artifact_bytes": MAX_ARTIFACT_BYTES}
    numbers = {
        "ingest_sequence",
        "input_events",
        "inserted_variants",
        "exact_retries",
        "conflict_variants",
        "last_sequence",
        "event_index",
        "version",
    }
    clocks = {"received_at", "recorded_at", "exchange_ts", "committed_at", "created_at"}
    for column in columns:
        name = '"' + column.replace('"', '""') + '"'
        if column in numbers or column in clocks:
            projection.append(name)
            continue
        cap = blobs.get(column, 65536 if column == "envelope_json" else 4096)
        size = f"octet_length({name})" if column in blobs else f"octet_length(encode({name}))"
        guard = f"({name} IS NULL OR {size}<={cap})"
        guards.append(guard)
        projection.append(f"CASE WHEN {guard} THEN {name} END")
    valid = " AND ".join(guards) or "TRUE"
    rows = conn.execute(
        f"SELECT {','.join(projection)},({valid}) FROM {table} WHERE {where} {order} LIMIT ?",
        [*args, limit + 1],
    ).fetchall()
    if len(rows) > limit or any(row[-1] is not True for row in rows):
        raise SupportReviewRequired("SUPPORT_BOUNDED_READ_INCOMPLETE")
    return [tuple(row[:-1]) for row in rows]


EVENT_COLUMNS = (
    "capture_event_id",
    "envelope_hash",
    "ingest_sequence",
    "source",
    "capture_session_id",
    "source_record_id",
    "received_at",
    "recorded_at",
    "exchange_ts",
    "payload",
    "payload_hash",
    "payload_format",
    "origin_kind",
    "envelope_json",
    "first_batch_key",
    "first_job_id",
)


def _verify_event(row: tuple[Any, ...]) -> None:
    if (
        not all(_pin(row[i]) for i in (0, 1, 10))
        or type(row[2]) is not int
        or row[2] <= 0
        or any(not _text(row[i], 4096) for i in (3, 4, 5, 11, 14, 15))
        or row[12] not in {"live_provider", "historical_import", "legacy_snapshot"}
        or not isinstance(row[9], bytes)
        or _hash(row[9]) != row[10]
        or not isinstance(row[13], str)
        or _hash(row[13].encode()) != row[1]
    ):
        raise SupportReviewRequired("SUPPORT_EVENT_CONTENT_INVALID")
    received = _instant(row[6])
    _instant(row[7])
    exchange = _instant(row[8]) if row[8] is not None else None
    value = _json(row[13])
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
    if not isinstance(value, dict) or set(value) != expected_keys:
        raise SupportReviewRequired("SUPPORT_ENVELOPE_SCHEMA_INVALID")
    expected = {
        "envelope_version": 1,
        "source": row[3],
        "capture_session_id": row[4],
        "source_record_id": row[5],
        "received_at": received,
        "payload_hash": row[10],
        "payload_format": row[11],
        "origin_kind": row[12],
        "exchange_ts": exchange,
        "provider_event_id": value["provider_event_id"],
        "instrument_ref": value["instrument_ref"],
    }
    if (
        _canonical(value) != row[13]
        or _canonical(value) != _canonical(expected)
        or _hash(_canonical(list(row[3:6])).encode()) != row[0]
        or any(
            value[k] is not None and not _text(value[k], 4096)
            for k in ("provider_event_id", "instrument_ref")
        )
    ):
        raise SupportReviewRequired("SUPPORT_ENVELOPE_LINK_OR_CLOCK_MISMATCH")


def _lifecycle(rows: list[tuple[Any, ...]]) -> str:
    if not rows or len(rows) > 6 or any(type(r[0]) is not int for r in rows):
        raise SupportReviewRequired("SUPPORT_LIFECYCLE_INVALID")
    if [r[0] for r in rows] != list(range(1, len(rows) + 1)):
        raise SupportReviewRequired("SUPPORT_EVENT_INDEX_INVALID")
    for _, _, clock, reason in rows:
        _instant(clock)
        if reason is not None and (
            not isinstance(reason, str) or not re.fullmatch(r"[A-Z0-9_]{1,64}", reason)
        ):
            raise SupportReviewRequired("SUPPORT_AUDIT_REASON_INVALID")
    states = tuple(r[1] for r in rows)
    if states in SUCCESS_PATHS and all(r[3] is None for r in rows):
        return "SUCCEEDED"
    if any(
        states == path[: len(states)] and len(states) < len(path) for path in SUCCESS_PATHS
    ) and all(r[3] is None for r in rows):
        return "INCOMPLETE"
    if (
        states[-1] in {"FAILED", "CANCELLED"}
        and any(
            states[:-1] == path[: len(states) - 1] and len(states) - 1 < len(path)
            for path in SUCCESS_PATHS
        )
        and len(states) >= 2
        and all(r[3] is None for r in rows[:-1])
    ):
        if states[-1] == "CANCELLED" and states[-2] == "PUBLISHED":
            raise SupportReviewRequired("SUPPORT_INVALID_PUBLISHED_CANCELLATION")
        return states[-1]
    raise SupportReviewRequired("SUPPORT_LIFECYCLE_INVALID")


def inspect_bronze_support(
    bronze: Any,
    *,
    support: BronzeSupportPin,
    expected_audit: IngestAuditExpectation,
) -> BronzeSupportEvidence:
    """Read-only current Bronze snapshot; no initialization, data acquisition or writes.

    @1 supports fresh all-new conflict-free batches only, with self-origin artifact.
    Generic retry/mixed-batch membership is not reconstructable from Bronze first
    links alone. Unsupported evidence requires review, never guessed membership.
    Expected audit metadata is caller-reviewed input, NOT authenticated ingest policy.
    """
    if not isinstance(support, BronzeSupportPin) or not isinstance(
        expected_audit, IngestAuditExpectation
    ):
        raise TypeError("TYPED_SUPPORT_AND_AUDIT_EXPECTATION_REQUIRED")
    BronzeSupportPin(**asdict(support))
    IngestAuditExpectation(**asdict(expected_audit))
    current = bronze.execute("SELECT current_database()").fetchone()
    if current is None or not any(
        r[1] == current[0] and r[2] for r in bronze.execute("PRAGMA database_list").fetchall()
    ):
        raise ValueError("FILE_BACKED_BRONZE_SUPPORT_REQUIRED")
    payload_ok = artifact_ok = membership_ok = origin_ok = audit_ok = False
    obligations: tuple[str, ...] = ()
    fingerprint = None
    reasons: tuple[str, ...] = ()
    bronze.execute("BEGIN TRANSACTION")
    try:
        for schema in ("bronze", "medallion_audit"):
            versions = bronze.execute(
                f"SELECT version FROM {_name(bronze, schema, 'schema_versions')} LIMIT 2"
            ).fetchall()
            if versions != [(1,)]:
                raise SupportReviewRequired("SUPPORT_SCHEMA_VERSION_NOT_SUPPORTED")
        if bronze.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_catalog=current_database() "
            "AND table_schema NOT IN ('bronze','medallion_audit') LIMIT 1"
        ).fetchone():
            raise SupportReviewRequired("DEDICATED_BRONZE_SUPPORT_DATABASE_REQUIRED")
        table = _name(bronze, "bronze", "event_variants")
        variants = _select(
            bronze, table, ("envelope_hash",), "capture_event_id=?", [support.capture_event_id], 2
        )
        if variants != [(support.envelope_hash,)]:
            raise SupportReviewRequired("SUPPORT_RECEIPT_CONFLICT_OR_PIN_MISSING")
        target_rows = _select(
            bronze,
            table,
            EVENT_COLUMNS,
            "capture_event_id=? AND envelope_hash=?",
            [support.capture_event_id, support.envelope_hash],
            1,
        )
        if not target_rows:
            raise SupportReviewRequired("SUPPORT_EVENT_MISSING")
        target = target_rows[0]
        _verify_event(target)
        if (
            target[10] != support.payload_hash
            or support.byte_end > len(target[9])
            or _hash(target[9][support.byte_start : support.byte_end]) != support.fragment_sha256
        ):
            raise SupportReviewRequired("SUPPORT_FRAGMENT_OR_PAYLOAD_PIN_MISMATCH")
        payload_ok = True
        batch_key, origin_job = target[14:16]
        batch_rows = _select(
            bronze,
            _name(bronze, "bronze", "ingest_batches"),
            (
                "batch_key",
                "batch_fingerprint",
                "input_file_hash",
                "input_events",
                "inserted_variants",
                "exact_retries",
                "conflict_variants",
                "last_sequence",
                "job_id",
                "committed_at",
            ),
            "batch_key=?",
            [batch_key],
            1,
        )
        if not batch_rows:
            raise SupportReviewRequired("SUPPORT_BATCH_MISSING")
        batch = batch_rows[0]
        if (
            not _pin(batch[1])
            or not _pin(batch[2])
            or batch[8] != origin_job
            or any(type(batch[i]) is not int for i in range(3, 8))
            or not 1 <= batch[3] <= MAX_BATCH_EVENTS
            or batch[4] != batch[3]
            or batch[5:7] != (0, 0)
        ):
            raise SupportReviewRequired("SUPPORT_FRESH_BATCH_PROFILE_NOT_ESTABLISHED")
        _instant(batch[9])
        capacity = bronze.execute(
            f"SELECT count(*),coalesce(sum(octet_length(payload)),0),"
            f"coalesce(max(octet_length(payload)),0) FROM {table} WHERE first_batch_key=?",
            [batch_key],
        ).fetchone()
        if (
            capacity[0] != batch[3]
            or capacity[1] > MAX_BATCH_BYTES
            or capacity[2] > MAX_PAYLOAD_BYTES
        ):
            raise SupportReviewRequired("SUPPORT_BATCH_CAPACITY_OR_COVERAGE_LIMIT")
        members = _select(
            bronze,
            table,
            EVENT_COLUMNS,
            "first_batch_key=?",
            [batch_key],
            MAX_BATCH_EVENTS,
            order="ORDER BY ingest_sequence",
        )
        if len(members) != batch[3] or len({r[2] for r in members}) != len(members):
            raise SupportReviewRequired("SUPPORT_BATCH_MEMBERSHIP_INCOMPLETE")
        for member in members:
            _verify_event(member)
            all_variants = _select(
                bronze, table, ("envelope_hash",), "capture_event_id=?", [member[0]], 2
            )
            if all_variants != [(member[1],)] or member[14:16] != (batch_key, origin_job):
                raise SupportReviewRequired("SUPPORT_BATCH_MEMBER_CONFLICT_OR_ORIGIN_MISMATCH")
        expected_batch = _hash(
            _canonical(
                {
                    "input_file_hash": batch[2],
                    "events": [[r[0], r[1]] for r in members],
                }
            ).encode()
        )
        if expected_batch != batch[1] or batch[7] != max(r[2] for r in members):
            raise SupportReviewRequired("SUPPORT_BATCH_FINGERPRINT_OR_CURSOR_MISMATCH")
        origin_batches = _select(
            bronze,
            _name(bronze, "bronze", "ingest_batches"),
            ("batch_key",),
            "job_id=?",
            [origin_job],
            2,
        )
        if origin_batches != [(batch_key,)]:
            raise SupportReviewRequired("SUPPORT_MULTI_BATCH_ORIGIN_JOB_NOT_SUPPORTED")
        membership_ok = True
        artifact_rows = _select(
            bronze,
            _name(bronze, "bronze", "input_artifacts"),
            (
                "artifact_hash",
                "artifact_bytes",
                "recorded_at",
                "first_job_id",
            ),
            "artifact_hash=?",
            [batch[2]],
            1,
        )
        if not artifact_rows or not isinstance(artifact_rows[0][1], bytes):
            raise SupportReviewRequired("SUPPORT_INPUT_ARTIFACT_MISSING")
        artifact = artifact_rows[0]
        _instant(artifact[2])
        if _hash(artifact[1]) != batch[2]:
            raise SupportReviewRequired("SUPPORT_INPUT_ARTIFACT_HASH_MISMATCH")
        if artifact[3] != origin_job:
            raise SupportReviewRequired("SUPPORT_REUSED_ARTIFACT_ORIGIN_NOT_SUPPORTED")
        artifact_ok = True
        jobs_table = _name(bronze, "medallion_audit", "jobs")
        jobs = _select(
            bronze,
            jobs_table,
            (
                "job_id",
                "parent_job_id",
                "command_name",
                "actor_id",
                "scope_ref",
                "code_revision",
                "config_hash",
                "created_at",
            ),
            "scope_ref=? OR job_id=?",
            [expected_audit.scope_ref, origin_job],
            MAX_JOBS,
            order="ORDER BY job_id",
        )
        job_ids = {job[0] for job in jobs}
        if not jobs or len(job_ids) != len(jobs) or origin_job not in job_ids:
            raise SupportReviewRequired("SUPPORT_INGEST_ORIGIN_JOB_MISSING")
        states: dict[str, str] = {}
        all_events: list[tuple[Any, ...]] = []
        for job in jobs:
            if (
                not _text(job[0], 128)
                or job[1] is not None
                or (job[2], job[4], job[6])
                != (
                    expected_audit.command_name,
                    expected_audit.scope_ref,
                    expected_audit.config_hash,
                )
                or not _text(job[3], 4096)
                or not _text(job[5], 4096)
            ):
                raise SupportReviewRequired("SUPPORT_INGEST_JOB_EXPECTATION_MISMATCH")
            _instant(job[7])
            events = _select(
                bronze,
                _name(bronze, "medallion_audit", "job_events"),
                (
                    "event_index",
                    "state",
                    "recorded_at",
                    "reason_code",
                ),
                "job_id=?",
                [job[0]],
                6,
                order="ORDER BY event_index",
            )
            states[job[0]] = _lifecycle(events)
            all_events.extend((job[0], *event) for event in events)
        if len(all_events) > MAX_EVENTS:
            raise SupportReviewRequired("SUPPORT_AUDIT_EVENT_LIMIT")
        origin_ok = states[origin_job] == "SUCCEEDED"
        obligations = tuple(sorted(job for job, state in states.items() if state != "SUCCEEDED"))
        if not origin_ok or obligations:
            raise SupportReviewRequired("SUPPORT_INGEST_AUDIT_OBLIGATIONS_REQUIRE_REVIEW")
        fingerprint = _hash(
            _canonical(
                [
                    VERSION,
                    asdict(support),
                    asdict(expected_audit),
                    target,
                    batch,
                    members,
                    artifact,
                    jobs,
                    all_events,
                ]
            ).encode()
        )
        audit_ok = True
        reasons = ("CURRENT_PINNED_BRONZE_STORAGE_AND_SCOPED_AUDIT_EVIDENCE_VERIFIED",)
    except SupportReviewRequired as error:
        reasons = (str(error),)
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError):
        reasons = ("SUPPORT_CONTENT_NOT_VERIFIED",)
    except BaseException:
        bronze.execute("ROLLBACK")
        raise
    bronze.execute("COMMIT")
    return BronzeSupportEvidence(
        VERSION,
        support.capture_event_id,
        "verified_storage_evidence" if audit_ok else "review_required",
        reasons,
        payload_ok,
        artifact_ok,
        membership_ok,
        origin_ok,
        audit_ok,
        obligations,
        fingerprint,
    )
