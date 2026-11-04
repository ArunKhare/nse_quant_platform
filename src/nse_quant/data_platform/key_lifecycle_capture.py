"""First-write audited retention of supplied lifecycle evidence, never key registration."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.observed_key_lifecycle import (
    KeyLifecycleRejected,
    LifecycleScope,
    ObservedKeyLifecycle,
    canonical,
    document,
    inspect_key_lifecycle,
    pin,
    sha,
    unhex,
)

if TYPE_CHECKING:
    from nse_quant.data_platform.lifecycle_scope_policy import LifecycleScopeAssessment
    from nse_quant.data_platform.statement_scope_policy import ScopeQuery

VERSION = "observed-key-lifecycle-capture@1"
COMMAND = "capture.observed_key_lifecycle@1"
MAX_INPUT_BYTES = 1048576
MAX_JOBS = 256
DEFINITION = (
    VERSION,
    "first-write-only exact signed records and supplied root retained",
    "no root authority, global latest, acquisition authenticity or key registration",
    "domain commit and final audit separate; no retries adoption repair or supersession",
)
DEFINITION_SHA256 = sha(canonical(DEFINITION))
TABLES = {("lifecycle_evidence", n) for n in ("schema_versions", "captures", "attempts")} | {
    ("medallion_audit", n) for n in ("schema_versions", "dataset_contracts", "jobs", "job_events")
}


def _name(conn: Any, schema: str, name: str) -> str:
    row = conn.execute("SELECT current_database()").fetchone()
    if row is None:
        raise KeyLifecycleRejected("LIFECYCLE_CAPTURE_CATALOG_UNAVAILABLE")
    return ".".join('"' + str(p).replace('"', '""') + '"' for p in (row[0], schema, name))


def _target(conn: Any, *, initialized: bool) -> None:
    row = conn.execute("SELECT current_database()").fetchone()
    if row is None or not any(
        r[1] == row[0] and r[2] for r in conn.execute("PRAGMA database_list").fetchall()
    ):
        raise KeyLifecycleRejected("LIFECYCLE_CAPTURE_FILE_BACKED_REQUIRED")
    inventory = conn.execute(
        "SELECT table_schema,table_name,table_type FROM information_schema.tables "
        "WHERE table_catalog=current_database() ORDER BY table_schema,table_name LIMIT 9"
    ).fetchall()
    known = {(s, t) for s, t, _kind in inventory}
    if (
        any(kind != "BASE TABLE" for _s, _t, kind in inventory)
        or known - TABLES
        or (initialized and known != TABLES)
    ):
        raise KeyLifecycleRejected("LIFECYCLE_CAPTURE_DEDICATED_INVENTORY_REQUIRED")


def encode_capture_input(
    records: tuple[bytes, ...],
    *,
    expected_record_sha256s: tuple[str, ...],
    root_public_key: bytes,
    expected_root_key_sha256: str,
    scope: LifecycleScope,
) -> tuple[bytes, ObservedKeyLifecycle]:
    observed = inspect_key_lifecycle(
        records,
        expected_record_sha256s=expected_record_sha256s,
        root_public_key=root_public_key,
        expected_root_key_sha256=expected_root_key_sha256,
        scope=scope,
    )
    raw = canonical(
        dict(
            version=VERSION,
            scope=asdict(scope),
            root_public_key_hex=root_public_key.hex(),
            expected_root_key_sha256=expected_root_key_sha256,
            expected_record_sha256s=expected_record_sha256s,
            records_hex=tuple(x.hex() for x in records),
        )
    )
    if len(raw) > MAX_INPUT_BYTES:
        raise KeyLifecycleRejected("LIFECYCLE_CAPTURE_INPUT_BOUND")
    return raw, observed


def decode_capture_input(raw: bytes) -> dict[str, Any]:
    value = document(raw, MAX_INPUT_BYTES)
    if (
        set(value)
        != {
            "version",
            "scope",
            "root_public_key_hex",
            "expected_root_key_sha256",
            "expected_record_sha256s",
            "records_hex",
        }
        or value["version"] != VERSION
    ):
        raise KeyLifecycleRejected("LIFECYCLE_CAPTURE_INPUT_SCHEMA")
    try:
        pins, records = value["expected_record_sha256s"], value["records_hex"]
        if (
            not isinstance(pins, list)
            or not isinstance(records, list)
            or not 1 <= len(pins) == len(records) <= 64
        ):
            raise KeyLifecycleRejected("LIFECYCLE_CAPTURE_INPUT_SHAPE")
        decoded: list[bytes] = []
        for text in records:
            if type(text) is not str or not 0 < len(text) <= 24576 or len(text) % 2:
                raise KeyLifecycleRejected("LIFECYCLE_CAPTURE_RECORD_BOUND")
            decoded.append(unhex(text, len(text) // 2))
        return dict(
            records=tuple(decoded),
            expected_record_sha256s=tuple(pins),
            root_public_key=unhex(value["root_public_key_hex"], 32),
            expected_root_key_sha256=value["expected_root_key_sha256"],
            scope=LifecycleScope(**value["scope"]),
        )
    except KeyLifecycleRejected:
        raise
    except (ValueError, TypeError, KeyError, RecursionError, OverflowError):
        raise KeyLifecycleRejected("LIFECYCLE_CAPTURE_INPUT_MALFORMED") from None


def capture_key_lifecycle(
    target: Any,
    *,
    records: tuple[bytes, ...],
    expected_record_sha256s: tuple[str, ...],
    root_public_key: bytes,
    expected_root_key_sha256: str,
    scope: LifecycleScope,
    actor_id: str,
    code_revision: str,
    initialize: bool = False,
) -> dict[str, str]:
    """Retain supplied bytes, not verified acquisition. Dedicated single-owner output.

    First-write-only: repeated calls are refused, including after final audit failure.
    No real authority/key registration or root activation. No caller lifecycle DTO import.
    """
    if any(
        type(x) is not str or not 1 <= len(x) <= 256 or not x.strip()
        for x in (actor_id, code_revision)
    ):
        raise KeyLifecycleRejected("LIFECYCLE_CAPTURE_EXECUTION_IDENTITIES_REQUIRED")
    raw, observed = encode_capture_input(
        records,
        expected_record_sha256s=expected_record_sha256s,
        root_public_key=root_public_key,
        expected_root_key_sha256=expected_root_key_sha256,
        scope=scope,
    )
    _target(target, initialized=not initialize)
    captures = _name(target, "lifecycle_evidence", "captures")
    attempts = _name(target, "lifecycle_evidence", "attempts")
    schema = _name(target, "lifecycle_evidence", "schema_versions")
    capture_id = sha(raw)
    ledger = AuditLedger(target)
    if initialize:
        ledger.initialize()
    jobs = _name(target, "medallion_audit", "jobs")
    exists = target.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_catalog=current_database() "
        "AND table_schema='lifecycle_evidence' AND table_name='captures'"
    ).fetchone()
    if (
        exists
        and target.execute(
            f"SELECT 1 FROM {captures} WHERE capture_id=?",
            [capture_id],
        ).fetchone()
    ):
        raise KeyLifecycleRejected("LIFECYCLE_CAPTURE_FIRST_WRITE_ONLY")
    if target.execute(
        f"SELECT 1 FROM {jobs} WHERE scope_ref=? LIMIT 1",
        ["sha256:" + capture_id],
    ).fetchone():
        raise KeyLifecycleRejected("LIFECYCLE_CAPTURE_PRIOR_OBLIGATION_REVIEW_REQUIRED")
    job = ledger.plan_job(
        command_name=COMMAND,
        actor_id=actor_id,
        code_revision=code_revision,
        scope_ref="sha256:" + capture_id,
        config_hash=DEFINITION_SHA256,
    )
    with ledger.execution(job):
        if initialize:
            target.execute("BEGIN TRANSACTION")
            try:
                target.execute(f"CREATE SCHEMA IF NOT EXISTS {captures.rsplit('.', 1)[0]}")
                target.execute(
                    f"CREATE TABLE IF NOT EXISTS {schema} "
                    "(version INTEGER PRIMARY KEY,definition_sha256 VARCHAR,"
                    "definition_bytes BLOB)"
                )
                rows = target.execute(
                    f"SELECT version,definition_sha256,CASE WHEN octet_length(definition_bytes)"
                    f"<=32768 THEN definition_bytes END FROM {schema} LIMIT 2"
                ).fetchall()
                if not rows:
                    target.execute(
                        f"INSERT INTO {schema} VALUES (1,?,?)",
                        [DEFINITION_SHA256, canonical(DEFINITION)],
                    )
                target.execute(
                    f"CREATE TABLE IF NOT EXISTS {captures} "
                    "(capture_id VARCHAR PRIMARY KEY,input_bytes BLOB NOT NULL,"
                    "result_bytes BLOB NOT NULL,"
                    "evidence_fingerprint VARCHAR NOT NULL,"
                    "recorded_at TIMESTAMPTZ NOT NULL,"
                    "first_job_id VARCHAR NOT NULL)"
                )
                target.execute(
                    f"CREATE TABLE IF NOT EXISTS {attempts} "
                    "(job_id VARCHAR PRIMARY KEY,capture_id VARCHAR NOT NULL)"
                )
                target.execute("COMMIT")
            except BaseException:
                target.execute("ROLLBACK")
                raise
        _target(target, initialized=True)
        if target.execute(
            f"SELECT version,definition_sha256,CASE WHEN octet_length(definition_bytes)<=32768 "
            f"THEN definition_bytes END FROM {schema} LIMIT 2"
        ).fetchall() != [
            (1, DEFINITION_SHA256, canonical(DEFINITION)),
        ]:
            raise KeyLifecycleRejected("LIFECYCLE_CAPTURE_SCHEMA_MISMATCH")
        if target.execute(f"SELECT 1 FROM {captures} WHERE capture_id=?", [capture_id]).fetchone():
            raise KeyLifecycleRejected("LIFECYCLE_CAPTURE_FIRST_WRITE_ONLY")
        # Earlier unlinked/failed work for this exact input must not be adopted or healed.
        jobs = _name(target, "medallion_audit", "jobs")
        prior = target.execute(
            f"SELECT job_id FROM {jobs} WHERE scope_ref=? AND job_id<>? LIMIT 1",
            ["sha256:" + capture_id, job],
        ).fetchone()
        if prior is not None:
            raise KeyLifecycleRejected("LIFECYCLE_CAPTURE_PRIOR_OBLIGATION_REVIEW_REQUIRED")
        target.execute("BEGIN TRANSACTION")
        try:
            target.execute(
                f"INSERT INTO {captures} VALUES (?,?,?,?,?,?)",
                [
                    capture_id,
                    raw,
                    canonical(asdict(observed)),
                    observed.evidence_fingerprint,
                    datetime.now(UTC),
                    job,
                ],
            )
            target.execute(f"INSERT INTO {attempts} VALUES (?,?)", [job, capture_id])
            target.execute("COMMIT")
        except BaseException:
            target.execute("ROLLBACK")
            raise
    return dict(
        capture_id=capture_id, evidence_fingerprint=observed.evidence_fingerprint, job_id=job
    )


@dataclass(frozen=True)
class RetainedKeyLifecycle:
    version: str
    capture_id: str
    input_bytes: bytes
    lifecycle: ObservedKeyLifecycle
    recording_verified: bool = True
    root_authority_authenticated: bool = False
    key_currentness_verified: bool = False
    authorized_revocation_asserted: bool = False
    decision_eligibility_asserted: bool = False


def read_key_lifecycle_capture(
    source: Any,
    *,
    capture_id: str,
    expected_evidence_fingerprint: str,
) -> RetainedKeyLifecycle:
    """Original recording verification only; use owned read-only connection, no outer tx.

    Every scoped job and link is checked before acceptance. No latest selection or cache.
    SQL failures propagate. Snapshot integrity cannot prevent privileged file rollback.
    """
    if not pin(capture_id) or not pin(expected_evidence_fingerprint):
        raise KeyLifecycleRejected("LIFECYCLE_CAPTURE_EXACT_PINS_REQUIRED")
    _target(source, initialized=True)
    captures = _name(source, "lifecycle_evidence", "captures")
    attempts = _name(source, "lifecycle_evidence", "attempts")
    jobs = _name(source, "medallion_audit", "jobs")
    events = _name(source, "medallion_audit", "job_events")
    schema = _name(source, "lifecycle_evidence", "schema_versions")
    source.execute("BEGIN TRANSACTION")
    try:
        audit_schema = _name(source, "medallion_audit", "schema_versions")
        audit_version = source.execute(f"SELECT version FROM {audit_schema} LIMIT 2").fetchall()
        version = source.execute(
            f"SELECT version,definition_sha256,CASE WHEN octet_length(definition_bytes)<=32768 "
            f"THEN definition_bytes END FROM {schema} LIMIT 2"
        ).fetchall()
        row = source.execute(
            f"SELECT CASE WHEN octet_length(input_bytes)<=? THEN input_bytes END,"
            "CASE WHEN octet_length(result_bytes)<=65536 THEN result_bytes END,"
            f"CASE WHEN length(evidence_fingerprint)<=64 THEN evidence_fingerprint END,"
            f"recorded_at,CASE WHEN length(first_job_id)<=128 THEN first_job_id END "
            f"FROM {captures} WHERE capture_id=?",
            [MAX_INPUT_BYTES, capture_id],
        ).fetchone()
        scoped = source.execute(
            f"SELECT CASE WHEN length(job_id)<=128 THEN job_id END,"
            "CASE WHEN length(command_name)<=128 THEN command_name END,"
            "CASE WHEN length(scope_ref)<=80 THEN scope_ref END,"
            "CASE WHEN length(config_hash)<=64 THEN config_hash END,"
            "CASE WHEN length(actor_id)<=256 THEN actor_id END,"
            "CASE WHEN length(code_revision)<=256 THEN code_revision END,created_at "
            f"FROM {jobs} WHERE scope_ref=? ORDER BY job_id LIMIT ?",
            ["sha256:" + capture_id, MAX_JOBS + 1],
        ).fetchall()
        linked = source.execute(
            f"SELECT CASE WHEN length(job_id)<=128 THEN job_id END "
            f"FROM {attempts} WHERE capture_id=? ORDER BY job_id LIMIT ?",
            [capture_id, MAX_JOBS + 1],
        ).fetchall()
        histories = source.execute(
            f"SELECT CASE WHEN length(e.job_id)<=128 THEN e.job_id END,"
            "e.event_index,CASE WHEN length(e.state)<=32 THEN e.state END,"
            "e.recorded_at,CASE WHEN e.reason_code IS NULL THEN NULL ELSE 'INVALID' END "
            f"FROM {events} e "
            f"JOIN {jobs} j ON j.job_id=e.job_id WHERE j.scope_ref=? "
            "ORDER BY e.job_id,e.event_index LIMIT ?",
            ["sha256:" + capture_id, MAX_JOBS * 4 + 1],
        ).fetchall()
        source.execute("COMMIT")
    except BaseException:
        source.execute("ROLLBACK")
        raise
    if audit_version != [(1,)] or version != [(1, DEFINITION_SHA256, canonical(DEFINITION))]:
        raise KeyLifecycleRejected("LIFECYCLE_CAPTURE_SCHEMA_MISMATCH")
    if (
        row is None
        or row[0] is None
        or row[1] is None
        or row[2] != expected_evidence_fingerprint
        or not _aware(row[3])
    ):
        raise KeyLifecycleRejected("LIFECYCLE_CAPTURE_RECORD_OR_PIN_MISMATCH")
    raw = bytes(row[0])
    if sha(raw) != capture_id:
        raise KeyLifecycleRejected("LIFECYCLE_CAPTURE_CHECKSUM_MISMATCH")
    if (
        not scoped
        or len(scoped) > MAX_JOBS
        or len(linked) > MAX_JOBS
        or len(histories) > MAX_JOBS * 4
        or row[4] not in {r[0] for r in scoped}
        or {r[0] for r in scoped} != {r[0] for r in linked}
    ):
        raise KeyLifecycleRejected("LIFECYCLE_CAPTURE_ATTEMPT_COVERAGE_REQUIRED")
    for item in scoped:
        if (
            item[1:4] != (COMMAND, "sha256:" + capture_id, DEFINITION_SHA256)
            or any(type(x) is not str or not x.strip() for x in item[4:6])
            or not _aware(item[6])
        ):
            raise KeyLifecycleRejected("LIFECYCLE_CAPTURE_JOB_MISMATCH")
        history = [r[1:] for r in histories if r[0] == item[0]]
        if (
            len(history) != 3
            or [r[0] for r in history] != [1, 2, 3]
            or [r[1] for r in history] != ["PLANNED", "RUNNING", "SUCCEEDED"]
            or any(not _aware(r[2]) or r[3] is not None for r in history)
        ):
            raise KeyLifecycleRejected("LIFECYCLE_CAPTURE_ORIGINAL_AUDIT_REQUIRED")
    arguments = decode_capture_input(raw)
    rebuilt_raw, observed = encode_capture_input(**arguments)
    if (
        rebuilt_raw != raw
        or observed.evidence_fingerprint != expected_evidence_fingerprint
        or canonical(asdict(observed)) != bytes(row[1])
    ):
        raise KeyLifecycleRejected("LIFECYCLE_CAPTURE_COMPLETE_REPLAY_MISMATCH")
    return RetainedKeyLifecycle(VERSION, capture_id, raw, observed)


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None
    )


def assess_retained_lifecycle_policy(
    source: Any,
    *,
    capture_id: str,
    expected_evidence_fingerprint: str,
    policy_bytes: bytes,
    policy_signature: bytes,
    expected_policy_sha256: str,
    query: ScopeQuery,
) -> LifecycleScopeAssessment:
    from nse_quant.data_platform.lifecycle_scope_policy import assess_lifecycle_scope_policy

    retained = read_key_lifecycle_capture(
        source,
        capture_id=capture_id,
        expected_evidence_fingerprint=expected_evidence_fingerprint,
    )
    return assess_lifecycle_scope_policy(
        **decode_capture_input(retained.input_bytes),
        policy_bytes=policy_bytes,
        policy_signature=policy_signature,
        expected_policy_sha256=expected_policy_sha256,
        query=query,
    )
