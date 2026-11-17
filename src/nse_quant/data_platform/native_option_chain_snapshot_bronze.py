"""Native option-chain snapshot Bronze; immutable retained artifact capture."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from nse_quant.data_platform import legacy_daily_rv_bronze as common
from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.bronze import BronzeEvent, BronzeEventStore
from nse_quant.data_platform.native_option_chain_snapshot import (
    VERSION as CODEC_VERSION,
)
from nse_quant.data_platform.native_option_chain_snapshot import (
    Rejected,
    canonical,
    derive_records,
    make_snapshot,
    pin,
    replay_snapshot,
    sha,
    snapshot_id,
)

VERSION = "native-option-chain-snapshot-bronze-recording@1"
COMMAND = "ingest.native_option_chain_snapshot@1"
SOURCE = "native_option_chain_snapshot_artifact"
DEFINITION = (
    VERSION,
    COMMAND,
    SOURCE,
    CODEC_VERSION,
    "source-label first write; retained artifact only; no market truth or policy authority",
)
ORIGIN_KINDS = ("live_provider", "historical_import")


def scope_id(source_label: str) -> str:
    if not isinstance(source_label, str) or not source_label.strip():
        raise Rejected("EXPLICIT_SOURCE_LABEL_REQUIRED")
    return sha(canonical([VERSION, source_label]))


def capture_option_chain_snapshot(payload: bytes, *, source_label: str) -> bytes:
    scope_id(source_label)
    document = _document(payload)
    if (
        not isinstance(document, dict)
        or set(document) != {"source_label", "snapshot"}
        or document.get("source_label") != source_label
    ):
        raise Rejected("SNAPSHOT_ENVELOPE_REQUIRED")
    return make_snapshot(source_label, document["snapshot"])


def _document(payload: bytes) -> dict[str, Any]:
    if not isinstance(payload, bytes) or not payload:
        raise Rejected("SNAPSHOT_BYTES_REQUIRED")
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Rejected("MALFORMED_SNAPSHOT") from exc
    return document


def preserve_option_chain_snapshot(
    bronze: Any,
    *,
    source_label: str,
    payload: bytes,
    expected_snapshot_id: str,
    imported_at: datetime,
    actor_id: str,
    code_revision: str,
    origin_kind: str,
) -> dict[str, Any]:
    if origin_kind not in ORIGIN_KINDS:
        raise Rejected("EXPLICIT_ORIGIN_KIND_REQUIRED")
    scope = scope_id(source_label)
    if not pin(expected_snapshot_id) or not common._actor(actor_id) or not common._revision(code_revision):
        raise Rejected("REVIEWED_REQUEST_REQUIRED")
    common._clock(imported_at)
    store = BronzeEventStore(bronze)
    store.verify_target()
    for table, field, value in (
        (common.name(bronze, "medallion_audit", "jobs"), "scope_ref", "sha256:" + scope),
        (store.object_name("event_variants"), "capture_session_id", scope),
        (store.object_name("ingest_batches"), "batch_key", scope),
        (store.object_name("input_artifacts"), "artifact_hash", expected_snapshot_id),
    ):
        if bronze.execute(f'SELECT 1 FROM {table} WHERE "{field}"=? LIMIT 1', [value]).fetchone():
            raise Rejected("FIRST_WRITE_ORIGINAL_OBLIGATION")
    ledger = AuditLedger(bronze)
    job = ledger.plan_job(
        command_name=COMMAND,
        actor_id=actor_id,
        code_revision=code_revision,
        scope_ref="sha256:" + scope,
        config_hash=sha(canonical([DEFINITION, expected_snapshot_id])),
    )
    with ledger.execution(job):
        first = capture_option_chain_snapshot(payload, source_label=source_label)
        if snapshot_id(first) != expected_snapshot_id:
            raise Rejected("REVIEWED_SNAPSHOT_CHANGED")
        second = capture_option_chain_snapshot(payload, source_label=source_label)
        if second != first:
            raise Rejected("SNAPSHOT_CHANGED_DURING_CAPTURE")
        event = BronzeEvent(
            SOURCE,
            scope,
            SOURCE,
            imported_at,
            first,
            CODEC_VERSION,
            origin_kind,
        )
        derive_records(
            first,
            snapshot_id=expected_snapshot_id,
            capture_event_id=event.capture_event_id,
            envelope_hash=event.envelope_hash,
        )
        receipt = store.append_batch((event,), batch_key=scope, input_artifact=first, job_id=job)
        if (
            receipt.inserted_variants != 1
            or receipt.exact_retries
            or receipt.conflict_variants
            or receipt.already_committed
        ):
            raise Rejected("UNEXPECTED_NATIVE_BATCH_REUSE")
    fingerprint, _raw = read_recording_bytes(
        bronze,
        source_label=source_label,
        snapshot_id=expected_snapshot_id,
        capture_event_id=event.capture_event_id,
        envelope_hash=event.envelope_hash,
    )
    return dict(
        source_label=source_label,
        snapshot_id=expected_snapshot_id,
        capture_event_id=event.capture_event_id,
        envelope_hash=event.envelope_hash,
        recording_fingerprint=fingerprint,
        row_count=len(
            derive_records(
                first,
                snapshot_id=expected_snapshot_id,
                capture_event_id=event.capture_event_id,
                envelope_hash=event.envelope_hash,
            )
        ),
        job_id=job,
        decision_eligibility_asserted=False,
    )


def read_recording_bytes(
    bronze: Any, *, source_label: str, snapshot_id: str, capture_event_id: str, envelope_hash: str
) -> tuple[str, bytes]:
    if not all(pin(value) for value in (snapshot_id, capture_event_id, envelope_hash)):
        raise Rejected("EXACT_BRONZE_PINS_REQUIRED")
    scope = scope_id(source_label)
    store = BronzeEventStore(bronze)
    store.verify_target()
    variants = store.object_name("event_variants")
    batches = store.object_name("ingest_batches")
    artifacts = store.object_name("input_artifacts")
    jobs = common.name(bronze, "medallion_audit", "jobs")
    events = common.name(bronze, "medallion_audit", "job_events")
    bronze.execute("BEGIN TRANSACTION")
    try:
        rows = bronze.execute(
            "SELECT CASE WHEN length(capture_event_id)<=64 THEN capture_event_id END,"
            "CASE WHEN length(envelope_hash)<=64 THEN envelope_hash END,"
            "CASE WHEN length(source)<=128 THEN source END,"
            "CASE WHEN length(capture_session_id)<=64 THEN capture_session_id END,"
            "CASE WHEN length(source_record_id)<=128 THEN source_record_id END,"
            "received_at,recorded_at,exchange_ts,"
            "CASE WHEN octet_length(payload)<=1048576 THEN payload END,"
            "CASE WHEN length(payload_hash)<=64 THEN payload_hash END,"
            "CASE WHEN length(payload_format)<=128 THEN payload_format END,"
            "CASE WHEN length(origin_kind)<=32 THEN origin_kind END,"
            "CASE WHEN octet_length(encode(envelope_json))<=8192 THEN envelope_json END,"
            "CASE WHEN length(first_batch_key)<=64 THEN first_batch_key END,"
            "CASE WHEN length(first_job_id)<=128 THEN first_job_id END,ingest_sequence "
            f"FROM {variants} WHERE capture_event_id=? OR capture_session_id=? LIMIT 3",
            [capture_event_id, scope],
        ).fetchall()
        if (
            len(rows) != 1
            or rows[0][:2] != (capture_event_id, envelope_hash)
            or rows[0][8] is None
            or rows[0][12] is None
        ):
            raise Rejected("EXACT_ORIGINAL_SNAPSHOT_VARIANT_REQUIRED")
        row = rows[0][2:]
        raw = bytes(row[6])
        document = replay_snapshot(raw, expected_snapshot_id=snapshot_id)
        event = BronzeEvent(SOURCE, scope, SOURCE, row[3], raw, CODEC_VERSION, row[9])
        if (
            document["source_label"] != source_label
            or row[:3] != (SOURCE, scope, SOURCE)
            or row[5] is not None
            or row[7:12] != (snapshot_id, CODEC_VERSION, row[9], event.envelope_json, scope)
            or event.capture_event_id != capture_event_id
            or event.envelope_hash != envelope_hash
        ):
            raise Rejected("NATIVE_SNAPSHOT_ENVELOPE_MISMATCH")
        scoped = common._metadata(
            bronze,
            "SELECT CASE WHEN length(job_id)<=128 THEN job_id END,"
            "CASE WHEN parent_job_id IS NULL THEN NULL ELSE 'PRESENT' END,"
            "CASE WHEN length(command_name)<=128 THEN command_name END,"
            "CASE WHEN length(actor_id)<=128 THEN actor_id END,"
            "CASE WHEN length(code_revision)<=40 THEN code_revision END,"
            "CASE WHEN length(config_hash)<=64 THEN config_hash END,created_at "
            f"FROM {jobs} WHERE scope_ref=?",
            ["sha256:" + scope],
            1,
        )
        history = common._metadata(
            bronze,
            "SELECT event_index,CASE WHEN length(state)<=32 THEN state END,recorded_at,"
            "CASE WHEN reason_code IS NULL THEN NULL ELSE 'PRESENT' END "
            f"FROM {events} WHERE job_id=? ORDER BY event_index",
            [row[12]],
            3,
        )
        batch = common._metadata(
            bronze,
            "SELECT CASE WHEN length(batch_fingerprint)<=64 THEN batch_fingerprint END,"
            "CASE WHEN length(input_file_hash)<=64 THEN input_file_hash END,input_events,"
            "inserted_variants,exact_retries,conflict_variants,last_sequence,"
            "CASE WHEN length(job_id)<=128 THEN job_id END,committed_at "
            f"FROM {batches} WHERE batch_key=?",
            [scope],
            1,
        )
        artifact = bronze.execute(
            "SELECT CASE WHEN octet_length(artifact_bytes)<=1048576 THEN artifact_bytes END,"
            "CASE WHEN length(first_job_id)<=128 THEN first_job_id END,recorded_at "
            f"FROM {artifacts} WHERE artifact_hash=? LIMIT 2",
            [snapshot_id],
        ).fetchall()
        bronze.execute("COMMIT")
    except BaseException:
        bronze.execute("ROLLBACK")
        raise
    config = sha(canonical([DEFINITION, snapshot_id]))
    if (
        len(scoped) != 1
        or scoped[0][0] != row[12]
        or scoped[0][1] is not None
        or scoped[0][2] != COMMAND
        or not common._actor(scoped[0][3])
        or not common._revision(scoped[0][4])
        or scoped[0][5] != config
        or [(h[0], h[1], h[3]) for h in history] != [(1, "PLANNED", None), (2, "RUNNING", None), (3, "SUCCEEDED", None)]
    ):
        raise Rejected("ORIGINAL_SNAPSHOT_AUDIT_NOT_VERIFIED")
    batch_fp = sha(canonical(dict(input_file_hash=snapshot_id, events=[(capture_event_id, envelope_hash)])))
    if (
        len(batch) != 1
        or batch[0][:8] != (batch_fp, snapshot_id, 1, 1, 0, 0, row[13], row[12])
        or type(row[13]) is not int
        or row[13] <= 0
        or len(artifact) != 1
        or artifact[0][0] is None
        or bytes(artifact[0][0]) != raw
        or artifact[0][1] != row[12]
    ):
        raise Rejected("ORIGINAL_SNAPSHOT_BATCH_NOT_VERIFIED")
    for at in [row[3], row[4], scoped[0][6], batch[0][8], artifact[0][2], *(h[2] for h in history)]:
        common._clock(at)
    metadata = [
        VERSION,
        capture_event_id,
        envelope_hash,
        list(row[:6]),
        sha(raw),
        list(row[7:]),
        scoped,
        history,
        batch,
        list(artifact[0][1:]),
    ]
    return sha(canonical(metadata)), raw


def read_option_chain_snapshot_bronze(
    bronze: Any,
    *,
    source_label: str,
    snapshot_id: str,
    capture_event_id: str,
    envelope_hash: str,
    expected_recording_fingerprint: str,
) -> tuple[bytes, ...]:
    if not pin(expected_recording_fingerprint):
        raise Rejected("EXACT_RECORDING_PIN_REQUIRED")
    common._readonly(bronze)
    fingerprint, raw = read_recording_bytes(
        bronze,
        source_label=source_label,
        snapshot_id=snapshot_id,
        capture_event_id=capture_event_id,
        envelope_hash=envelope_hash,
    )
    if fingerprint != expected_recording_fingerprint:
        raise Rejected("SNAPSHOT_RECORDING_FINGERPRINT_CHANGED")
    return derive_records(
        raw,
        snapshot_id=snapshot_id,
        capture_event_id=capture_event_id,
        envelope_hash=envelope_hash,
    )


def revalidate_option_chain_snapshot_source(payload: bytes, bronze: Any, **pins: Any) -> tuple[bytes, ...]:
    common._separate(None, bronze)
    first = read_option_chain_snapshot_bronze(bronze, **pins)
    for _ in range(2):
        if (
            snapshot_id(capture_option_chain_snapshot(payload, source_label=pins["source_label"]))
            != pins["snapshot_id"]
        ):
            raise Rejected("CURRENT_NATIVE_SNAPSHOT_CHANGED")
    second = read_option_chain_snapshot_bronze(bronze, **pins)
    if first != second:
        raise Rejected("SNAPSHOT_RECORDING_CHANGED_DURING_REVALIDATION")
    return second
