"""Explicit native VIX retention. No capture activation, publication or trading hooks.

Caller exclusively owns writer connections; no ambient transaction is permitted.
Audit/domain commits are separate. Interrupted original writes fail verification;
this module never silently heals them. Open independent read-only replay handles.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from nse_quant.data_platform import legacy_silver_common as base
from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.bronze import BronzeEvent, BronzeEventStore
from nse_quant.market_data.india_vix_inputs import VERSION as NORMALIZER_VERSION
from nse_quant.market_data.india_vix_inputs import RawVixCapture, normalize_vix_capture

VERSION = "native-india-vix-recording@1"
SOURCE = "kite_india_vix"
CAPTURE = "capture.india_vix@1"
NORMALIZE = "persist.india_vix_silver@1"
SETS = "silver.india_vix_sets"
RECORDS = "silver.india_vix_records"
ATTEMPTS = "silver.india_vix_attempts"
MAX_BYTES = 1048576


def instant(value: datetime) -> str:
    base.clock(value)
    return value.astimezone(UTC).isoformat()


def canonical(value: Any) -> bytes:
    def convert(item: Any) -> Any:
        if isinstance(item, datetime):
            return instant(item)
        if isinstance(item, dict):
            return {key: convert(val) for key, val in item.items()}
        if isinstance(item, (list, tuple)):
            return [convert(val) for val in item]
        return item

    return base.canonical(convert(value))


def one(conn: Any, sql: str, args: list[Any]) -> tuple[Any, ...]:
    rows = conn.execute(sql + " LIMIT 2", args).fetchall()
    if len(rows) != 1:
        raise ValueError("EXACT_RECORD_REQUIRED")
    return tuple(rows[0])


def table(conn: Any, name: str) -> str:
    catalog = one(conn, "SELECT current_database()", [])[0]
    schema, obj = name.split(".")
    return ".".join('"' + part.replace('"', '""') + '"' for part in (catalog, schema, obj))


def execution(owner: str, revision: str) -> None:
    if not base.actor(owner) or not base.revision(revision):
        raise ValueError("WRITER_OWNER_AND_CODE_REVISION_REQUIRED")


def audit(conn: Any, job: str, command: str, scope: str, config: str) -> list[Any]:
    jobs = table(conn, "medallion_audit.jobs")
    events = table(conn, "medallion_audit.job_events")
    row = one(
        conn,
        f"SELECT command_name,scope_ref,config_hash,actor_id,code_revision,"
        f"created_at,parent_job_id FROM {jobs} WHERE job_id=?",
        [job],
    )
    execution(row[3], row[4])
    if row[:3] != (command, scope, config) or row[6] is not None:
        raise ValueError("VIX_AUDIT_IDENTITY_MISMATCH")
    history = conn.execute(
        f"SELECT event_index,state,recorded_at,reason_code FROM {events} WHERE job_id=? ORDER BY event_index", [job]
    ).fetchall()
    if [(r[0], r[1], r[3]) for r in history] != [(1, "PLANNED", None), (2, "RUNNING", None), (3, "SUCCEEDED", None)]:
        raise ValueError("SUCCESSFUL_ORIGINAL_AUDIT_REQUIRED")
    times = [row[5], *(r[2] for r in history)]
    for at in times:
        base.clock(at)
    if times != sorted(times):
        raise ValueError("VIX_AUDIT_TIME_ORDER")
    return [list(row), history]


@dataclass(frozen=True)
class VixBronzePins:
    capture_event_id: str
    envelope_hash: str
    recording_fingerprint: str

    def __post_init__(self) -> None:
        if not all(base.pin(value) for value in asdict(self).values()):
            raise ValueError("EXACT_VIX_BRONZE_PINS_REQUIRED")


def event_for(capture: RawVixCapture, session: str, record: str) -> BronzeEvent:
    raw = canonical(dict(version=VERSION, capture=asdict(capture)))
    if len(raw) > MAX_BYTES:
        raise ValueError("VIX_CAPTURE_BOUND")
    # Retain source timestamp exactly inside payload_json; do not assert exchange_ts
    # for potentially invalid input. This is decoded provider JSON, not wire bytes.
    return BronzeEvent(SOURCE, session, record, capture.received_at, raw, VERSION, "live_provider")


def initialize_vix_bronze(conn: Any, *, writer_owner: str) -> None:
    execution(writer_owner, "0" * 40)
    BronzeEventStore(conn).initialize()
    AuditLedger(conn).initialize()


def _bronze(conn: Any, event_id: str, envelope: str) -> tuple[str, RawVixCapture]:
    store = BronzeEventStore(conn)
    store.verify_target()
    row = one(
        conn,
        f"SELECT capture_event_id,envelope_hash,source,capture_session_id,source_record_id,"
        "received_at,recorded_at,exchange_ts,CASE WHEN octet_length(payload)<=1048576 THEN payload END,"
        "payload_hash,payload_format,origin_kind,"
        "envelope_json,first_batch_key,first_job_id,ingest_sequence "
        f"FROM {store.object_name('event_variants')} WHERE capture_event_id=?",
        [event_id],
    )
    if row[8] is None:
        raise ValueError("VIX_CAPTURE_BOUND")
    raw = bytes(row[8])
    if row[:2] != (event_id, envelope) or len(raw) > MAX_BYTES:
        raise ValueError("VIX_VARIANT_OR_BOUND_MISMATCH")
    doc = json.loads(raw)
    if set(doc) != {"version", "capture"} or doc["version"] != VERSION:
        raise ValueError("VIX_CAPTURE_VERSION_MISMATCH")
    fields = doc["capture"]
    fields["requested_at"] = datetime.fromisoformat(fields["requested_at"])
    fields["received_at"] = datetime.fromisoformat(fields["received_at"])
    capture = RawVixCapture(**fields)
    event = event_for(capture, row[3], row[4])
    if (
        event.capture_event_id != event_id
        or event.envelope_hash != envelope
        or event.payload != raw
        or row[2] != SOURCE
        or row[5] != capture.received_at
        or row[7] is not None
        or row[9:13] != (event.payload_hash, VERSION, "live_provider", event.envelope_json)
        or row[13] != envelope
        or type(row[15]) is not int
        or row[15] <= 0
    ):
        raise ValueError("VIX_ENVELOPE_INTEGRITY_MISMATCH")
    batch = one(
        conn,
        f"SELECT batch_fingerprint,input_file_hash,input_events,inserted_variants,"
        "exact_retries,conflict_variants,last_sequence,job_id,committed_at "
        f"FROM {store.object_name('ingest_batches')} WHERE batch_key=?",
        [envelope],
    )
    expected = base.sha(base.canonical(dict(input_file_hash=event.payload_hash, events=[(event_id, envelope)])))
    if (
        batch[:6] != (expected, event.payload_hash, 1, 1, 0, 0)
        or batch[7] != row[14]
        or type(batch[6]) is not int
        or batch[6] < row[15]
    ):
        raise ValueError("VIX_BATCH_INTEGRITY_MISMATCH")
    artifact = one(
        conn,
        f"SELECT artifact_bytes,first_job_id,recorded_at "
        f"FROM {store.object_name('input_artifacts')} WHERE artifact_hash=?",
        [event.payload_hash],
    )
    if bytes(artifact[0]) != raw:
        raise ValueError("VIX_ARTIFACT_INTEGRITY_MISMATCH")
    history = audit(conn, row[14], CAPTURE, event_id, event.payload_hash)
    for at in (row[6], batch[8], artifact[2]):
        base.clock(at)
    if not history[1][1][2] <= row[6] <= batch[8] <= history[1][2][2]:
        raise ValueError("VIX_RECORDING_TIME_ORDER")
    fingerprint = base.sha(
        canonical(
            [
                VERSION,
                list(row[:8]),
                base.sha(raw),
                list(row[9:]),
                list(batch),
                [base.sha(bytes(artifact[0])), *artifact[1:]],
                history,
            ]
        )
    )
    return fingerprint, capture


def preserve_vix_capture(
    conn: Any,
    capture: RawVixCapture,
    *,
    capture_session_id: str,
    source_record_id: str,
    writer_owner: str,
    code_revision: str,
) -> dict[str, Any]:
    """Exact retry reuses batch; changed evidence is retained and both variants quarantined."""
    execution(writer_owner, code_revision)
    event = event_for(capture, capture_session_id, source_record_id)
    store = BronzeEventStore(conn)
    store.verify_target()
    ledger = AuditLedger(conn)
    job = ledger.plan_job(
        command_name=CAPTURE,
        actor_id=writer_owner,
        code_revision=code_revision,
        scope_ref=event.capture_event_id,
        config_hash=event.payload_hash,
    )
    with ledger.execution(job):
        receipt = store.append_batch((event,), batch_key=event.envelope_hash, input_artifact=event.payload, job_id=job)
    conflicted = event.capture_event_id in store.conflicting_event_ids()
    pins = None
    if not conflicted:
        fingerprint, _ = _bronze(conn, event.capture_event_id, event.envelope_hash)
        pins = VixBronzePins(event.capture_event_id, event.envelope_hash, fingerprint)
    return dict(pins=pins, receipt=receipt, conflicted=conflicted, job_id=job, decision_eligibility_asserted=False)


def read_vix_bronze(reader: Any, *, pins: VixBronzePins) -> RawVixCapture:
    base.readonly(reader)
    reader.execute("BEGIN TRANSACTION")
    try:
        fingerprint, capture = _bronze(reader, pins.capture_event_id, pins.envelope_hash)
        if fingerprint != pins.recording_fingerprint:
            raise ValueError("VIX_BRONZE_RECORDING_PIN_MISMATCH")
        reader.execute("COMMIT")
    except BaseException:
        reader.execute("ROLLBACK")
        raise
    return capture


def silver_target(conn: Any) -> None:
    forbidden = conn.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_catalog=current_database() AND "
        "table_schema NOT IN ('silver','medallion_audit')"
    ).fetchall()
    if forbidden:
        raise ValueError("DEDICATED_SILVER_TARGET_REQUIRED")


def initialize_vix_silver(conn: Any, *, writer_owner: str) -> None:
    execution(writer_owner, "0" * 40)
    silver_target(conn)
    AuditLedger(conn).initialize()
    sets, records, attempts = (table(conn, name) for name in (SETS, RECORDS, ATTEMPTS))
    schema = sets.rsplit(".", 1)[0]
    conn.execute("BEGIN TRANSACTION")
    try:
        conn.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS {sets} (revision_id VARCHAR PRIMARY KEY,"
            "context BLOB NOT NULL,context_sha256 VARCHAR NOT NULL,recorded_at TIMESTAMPTZ NOT NULL)"
        )
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS {records} (revision_id VARCHAR NOT NULL,ordinal BIGINT NOT NULL,"
            "record_bytes BLOB NOT NULL,recorded_at TIMESTAMPTZ NOT NULL,PRIMARY KEY(revision_id,ordinal))"
        )
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS {attempts} (revision_id VARCHAR PRIMARY KEY,recorded_at TIMESTAMPTZ NOT NULL)"
        )
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def observe_vix_bronze(
    bronze: Any, *, pins: VixBronzePins, as_of: datetime, max_age_seconds: float = 300
) -> tuple[bytes, bytes]:
    if (
        isinstance(max_age_seconds, bool)
        or not isinstance(max_age_seconds, (int, float))
        or not math.isfinite(max_age_seconds)
        or max_age_seconds <= 0
    ):
        raise ValueError("INVALID_FRESHNESS_POLICY")
    policy = dict(as_of=instant(as_of), max_age_seconds=float(max_age_seconds), session_is_open=None)
    capture = read_vix_bronze(bronze, pins=pins)
    try:
        observed = normalize_vix_capture(capture, as_of=as_of, max_age_seconds=max_age_seconds, session_is_open=None)
    except (ValueError, TypeError, KeyError, OverflowError) as error:
        known = {
            "future_or_unordered_capture",
            "raw_payload_hash_mismatch",
            "instrument_reference_hash_mismatch",
            "vix_reference_identity_mismatch",
            "vix_quote_identity_mismatch",
            "invalid_vix_value",
            "vix_source_timestamp_missing",
            "future_or_stale_vix",
        }
        reason = str(error) if str(error) in known else "NORMALIZATION_REJECTED"
        record = canonical(
            dict(
                quality_state="rejected", rejection_reason=reason, observation=None, decision_eligibility_asserted=False
            )
        )
    else:
        record = canonical(
            dict(
                quality_state="valid_observation",
                rejection_reason=None,
                observation=asdict(observed),
                decision_eligibility_asserted=False,
            )
        )
    context = base.canonical(
        dict(
            version=VERSION,
            normalizer_version=NORMALIZER_VERSION,
            iv30_source="india_vix",
            units=dict(source="percent", iv30="decimal"),
            pins=asdict(pins),
            policy=policy,
            record_hashes=[base.sha(record)],
        )
    )
    return context, record


def _silver(conn: Any, revision_id: str) -> tuple[bytes, bytes]:
    if not base.pin(revision_id):
        raise ValueError("EXACT_VIX_SILVER_REVISION_REQUIRED")
    sets, records, attempts = (table(conn, name) for name in (SETS, RECORDS, ATTEMPTS))
    raw, digest = one(conn, f"SELECT context,context_sha256 FROM {sets} WHERE revision_id=?", [revision_id])
    ordinal, value = one(conn, f"SELECT ordinal,record_bytes FROM {records} WHERE revision_id=?", [revision_id])
    context, record = bytes(raw), bytes(value)
    doc = json.loads(context)
    if (
        len(context) > MAX_BYTES
        or len(record) > MAX_BYTES
        or ordinal != 0
        or base.canonical(doc) != context
        or base.sha(context) != digest
        or doc.get("record_hashes") != [base.sha(record)]
        or doc.get("version") != VERSION
        or doc.get("normalizer_version") != NORMALIZER_VERSION
        or base.sha(base.canonical([VERSION, digest])) != revision_id
    ):
        raise ValueError("VIX_SILVER_INTEGRITY_MISMATCH")
    base.verify_recording(
        conn,
        command=NORMALIZE,
        scope_ref=SOURCE,
        config_hash=digest,
        revision_id=revision_id,
        sets_table=sets,
        observations_table=records,
        attempts_table=attempts,
        observation_count=1,
    )
    return context, record


def persist_vix_silver(
    bronze: Any,
    target: Any,
    *,
    pins: VixBronzePins,
    as_of: datetime,
    expected_context_sha256: str,
    writer_owner: str,
    code_revision: str,
    max_age_seconds: float = 300,
) -> dict[str, Any]:
    execution(writer_owner, code_revision)
    base.separate(bronze, target)
    silver_target(target)
    context, record = observe_vix_bronze(bronze, pins=pins, as_of=as_of, max_age_seconds=max_age_seconds)
    if not base.pin(expected_context_sha256) or base.sha(context) != expected_context_sha256:
        raise ValueError("REVIEWED_VIX_CONTEXT_CHANGED")
    revision_id = base.sha(base.canonical([VERSION, expected_context_sha256]))
    sets, records, attempts = (table(target, name) for name in (SETS, RECORDS, ATTEMPTS))
    if target.execute(f"SELECT 1 FROM {sets} WHERE revision_id=?", [revision_id]).fetchone():
        if _silver(target, revision_id) != (context, record):
            raise ValueError("VIX_SILVER_RETRY_CONFLICT")
        return dict(revision_id=revision_id, exact_retry=True, decision_eligibility_asserted=False)
    ledger = AuditLedger(target)
    job = ledger.plan_job(
        command_name=NORMALIZE,
        actor_id=writer_owner,
        code_revision=code_revision,
        scope_ref=SOURCE,
        config_hash=expected_context_sha256,
    )
    with ledger.execution(job):
        if observe_vix_bronze(bronze, pins=pins, as_of=as_of, max_age_seconds=max_age_seconds) != (context, record):
            raise ValueError("VIX_SOURCE_CHANGED")
        target.execute("BEGIN TRANSACTION")
        try:
            now = datetime.now(UTC)
            target.execute(f"INSERT INTO {sets} VALUES (?,?,?,?)", [revision_id, context, expected_context_sha256, now])
            target.execute(f"INSERT INTO {records} VALUES (?,?,?,?)", [revision_id, 0, record, now])
            target.execute(f"INSERT INTO {attempts} VALUES (?,?)", [revision_id, now])
            target.execute("COMMIT")
        except BaseException:
            target.execute("ROLLBACK")
            raise
    return dict(revision_id=revision_id, exact_retry=False, job_id=job, decision_eligibility_asserted=False)


def replay_vix_silver(bronze: Any, silver: Any, *, revision_id: str) -> dict[str, Any]:
    base.separate(bronze, silver)
    base.readonly(bronze)
    base.readonly(silver)
    context, record = _silver(silver, revision_id)
    doc = json.loads(context)
    policy = doc["policy"]
    if policy["session_is_open"] is not None:
        raise ValueError("UNSUPPORTED_CALENDAR_AUTHORITY")
    reproduced = observe_vix_bronze(
        bronze,
        pins=VixBronzePins(**doc["pins"]),
        as_of=datetime.fromisoformat(policy["as_of"]),
        max_age_seconds=policy["max_age_seconds"],
    )
    if reproduced != (context, record):
        raise ValueError("VIX_REPLAY_MISMATCH")
    return json.loads(record)
