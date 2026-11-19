"""Persisted source-linked evidence-snapshots Silver over the actual Bronze reader."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from nse_quant.data_platform import legacy_silver_common as base
from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.legacy_evidence_snapshot_bronze import read_evidence_snapshot_bronze
from nse_quant.data_platform.legacy_evidence_snapshots import Rejected, sha

VERSION = "legacy-evidence-snapshots-silver-recording@1"
COMMAND = "normalize.legacy_evidence_snapshots@1"
TABLE = "evidence_snapshots"
OBSERVATIONS = "evidence_snapshot_observations"
SETS = "evidence_snapshot_sets"
ATTEMPTS = "evidence_snapshot_attempts"
MAX_CONTEXT = 2200000
MAX_RECORD = 512 * 1024
MAX_RECORDS = 4 * 1024 * 1024
MAX_SCALAR = 64 * 1024
MAX_SCALARS = 1024 * 1024
DEFINITION = (VERSION, COMMAND, "derived only from reviewed evidence-snapshots Bronze recording")


@dataclass(frozen=True)
class EvidenceSnapshotBronzePins:
    source_label: str
    snapshot_id: str
    capture_event_id: str
    envelope_hash: str
    recording_fingerprint: str

    @property
    def scope_id(self) -> str:
        return base.sha(base.canonical([VERSION, self.source_label]))

    def reader_args(self) -> dict[str, str]:
        return dict(
            source_label=self.source_label,
            snapshot_id=self.snapshot_id,
            capture_event_id=self.capture_event_id,
            envelope_hash=self.envelope_hash,
            expected_recording_fingerprint=self.recording_fingerprint,
        )


def scope_id(source_label: str) -> str:
    return base.sha(base.canonical([VERSION, source_label]))


def initialize_evidence_snapshots_silver(target: Any) -> None:
    AuditLedger(target).initialize()
    target.execute("CREATE SCHEMA IF NOT EXISTS silver")
    target.execute(
        f"CREATE TABLE IF NOT EXISTS silver.silver.{SETS} ("
        "revision_id VARCHAR PRIMARY KEY,context BLOB NOT NULL,"
        "context_sha256 VARCHAR NOT NULL,recorded_at TIMESTAMPTZ NOT NULL)"
    )
    target.execute(
        f"CREATE TABLE IF NOT EXISTS silver.silver.{OBSERVATIONS} ("
        "revision_id VARCHAR NOT NULL,ordinal BIGINT NOT NULL,"
        "run_id VARCHAR NOT NULL,"
        "ts TIMESTAMPTZ NOT NULL,"
        "symbol VARCHAR,"
        "plugin_name VARCHAR NOT NULL,"
        "payload_json VARCHAR,"
        "record_bytes BLOB NOT NULL,recorded_at TIMESTAMPTZ NOT NULL,"
        "PRIMARY KEY(revision_id,ordinal),"
        "UNIQUE(revision_id,run_id,ts,plugin_name))"
    )
    target.execute(
        f"CREATE TABLE IF NOT EXISTS silver.silver.{ATTEMPTS} ("
        "revision_id VARCHAR PRIMARY KEY,recorded_at TIMESTAMPTZ NOT NULL)"
    )


def observe_evidence_snapshots_bronze(bronze: Any, *, pins: EvidenceSnapshotBronzePins) -> bytes:
    if not base.pin(pins.recording_fingerprint):
        raise Rejected("EXACT_EVIDENCE_SNAPSHOTS_SILVER_BRONZE_PIN_REQUIRED")
    base.readonly(bronze)
    records = read_evidence_snapshot_bronze(bronze, **pins.reader_args())
    if not 1 <= len(records) <= 1000:
        raise Rejected("EVIDENCE_SNAPSHOTS_SILVER_ROW_BOUND")
    context = base.canonical(
        dict(
            version=VERSION,
            pins={
                "source_label": pins.source_label,
                "snapshot_id": pins.snapshot_id,
                "capture_event_id": pins.capture_event_id,
                "envelope_hash": pins.envelope_hash,
                "recording_fingerprint": pins.recording_fingerprint,
            },
            record_hashes=[sha(record) for record in records],
        )
    )
    if len(context) > MAX_CONTEXT:
        raise Rejected("EVIDENCE_SNAPSHOTS_SILVER_CONTEXT_BOUND")
    return context


def persist_evidence_snapshots_silver(
    bronze: Any,
    target: Any,
    *,
    pins: EvidenceSnapshotBronzePins,
    expected_context_sha256: str,
    actor_id: str,
    code_revision: str,
) -> dict[str, Any]:
    if (
        not base.pin(expected_context_sha256)
        or not base.actor(actor_id)
        or not base.revision(code_revision)
    ):
        raise Rejected("REVIEWED_EVIDENCE_SNAPSHOTS_SILVER_REQUEST_REQUIRED")
    base.separate(bronze, target)
    base.readonly(bronze)
    revision_id = base.sha(
        base.canonical([VERSION, pins.scope_id, pins.capture_event_id, expected_context_sha256])
    )
    for table, field in (
        (f"silver.silver.{SETS}", "revision_id"),
        (f"silver.silver.{ATTEMPTS}", "revision_id"),
    ):
        if target.execute(
            f"SELECT 1 FROM {table} WHERE {field}=? LIMIT 1", [revision_id]
        ).fetchone():
            raise Rejected("EVIDENCE_SNAPSHOTS_SILVER_FIRST_WRITE_ORIGINAL_OBLIGATION")
    ledger = AuditLedger(target)
    job = ledger.plan_job(
        command_name=COMMAND,
        actor_id=actor_id,
        code_revision=code_revision,
        scope_ref="sha256:" + scope_id(pins.source_label),
        config_hash=expected_context_sha256,
    )
    with ledger.execution(job):
        first = observe_evidence_snapshots_bronze(bronze, pins=pins)
        if sha(first) != expected_context_sha256:
            raise Rejected("REVIEWED_EVIDENCE_SNAPSHOTS_BRONZE_CONTEXT_CHANGED")
        second = observe_evidence_snapshots_bronze(bronze, pins=pins)
        if second != first:
            raise Rejected("EVIDENCE_SNAPSHOTS_BRONZE_CONTEXT_DRIFT")
        records = read_evidence_snapshot_bronze(bronze, **pins.reader_args())
        materialized = []
        total_scalar = 0
        total_record = 0
        for ordinal, record in enumerate(records):
            if len(record) > MAX_RECORD:
                raise Rejected("EVIDENCE_SNAPSHOTS_SILVER_RECORD_BOUND")
            total_record += len(record)
            if total_record > MAX_RECORDS:
                raise Rejected("EVIDENCE_SNAPSHOTS_SILVER_AGGREGATE_BOUND")
            document = __import__("json").loads(record)
            fields = document["stored_fields"]
            run_id, ts, symbol, plugin_name, payload_json = (
                fields["run_id"],
                fields["ts"],
                fields["symbol"],
                fields["plugin_name"],
                fields["payload_json"],
            )
            for _, value in (("run_id", run_id), ("plugin_name", plugin_name)):
                if type(value) is not str or not 0 < len(value.encode()) <= MAX_SCALAR:
                    raise Rejected("EVIDENCE_SNAPSHOTS_SILVER_KEY_REQUIRED")
                total_scalar += len(value.encode())
            if type(ts) is not str:
                raise Rejected("EVIDENCE_SNAPSHOTS_SILVER_INSTANT_TEXT_REQUIRED")
            instant = datetime.fromisoformat(ts)
            if instant.tzinfo is None or instant.utcoffset() is None:
                raise Rejected("EVIDENCE_SNAPSHOTS_SILVER_AWARE_INSTANT_REQUIRED")
            if symbol is not None:
                if type(symbol) is not str or len(symbol.encode()) > MAX_SCALAR:
                    raise Rejected("EVIDENCE_SNAPSHOTS_SILVER_TEXT_REQUIRED")
                total_scalar += len(symbol.encode())
            if payload_json is not None:
                if type(payload_json) is not str or len(payload_json.encode()) > MAX_SCALAR:
                    raise Rejected("EVIDENCE_SNAPSHOTS_SILVER_TEXT_REQUIRED")
                total_scalar += len(payload_json.encode())
            if total_scalar > MAX_SCALARS:
                raise Rejected("EVIDENCE_SNAPSHOTS_SILVER_SCALAR_AGGREGATE_BOUND")
            materialized.append(
                (ordinal, run_id, instant, symbol, plugin_name, payload_json, record)
            )
        target.execute("BEGIN TRANSACTION")
        try:
            target.execute(
                f"INSERT INTO silver.silver.{SETS} VALUES (?,?,?,?)",
                [revision_id, first, expected_context_sha256, base.clock(datetime.now(UTC))],
            )
            for row in materialized:
                target.execute(
                    f"INSERT INTO silver.silver.{OBSERVATIONS} VALUES (?,?,?,?,?,?,?,?,?)",
                    [revision_id, *row, base.clock(datetime.now(UTC))],
                )
            target.execute(
                f"INSERT INTO silver.silver.{ATTEMPTS} VALUES (?,?)",
                [revision_id, base.clock(datetime.now(UTC))],
            )
            target.execute("COMMIT")
        except BaseException:
            target.execute("ROLLBACK")
            raise
    fingerprint, _ = _read_recording(target, revision_id=revision_id)
    return dict(
        revision_id=revision_id,
        recording_fingerprint=fingerprint,
        row_count=len(records),
        job_id=job,
        decision_eligibility_asserted=False,
    )


def _read_recording(target: Any, *, revision_id: str) -> tuple[str, bytes]:
    if not base.pin(revision_id):
        raise Rejected("EXACT_EVIDENCE_SNAPSHOTS_SILVER_REVISION_PIN_REQUIRED")
    rows = base.metadata(
        target,
        f"SELECT CASE WHEN octet_length(context)<=? THEN context END,"
        f"CASE WHEN length(context_sha256)<=64 THEN context_sha256 END,recorded_at "
        f"FROM silver.silver.{SETS} WHERE revision_id=?",
        [MAX_CONTEXT, revision_id],
        1,
    )
    context = bytes(rows[0][0])
    if rows[0][1] != sha(context):
        raise Rejected("EVIDENCE_SNAPSHOTS_SILVER_CONTEXT_HASH_MISMATCH")
    base.clock(rows[0][2])
    return sha(base.canonical([VERSION, revision_id, context.hex()])), context


def read_evidence_snapshots_silver(
    reader: Any, *, revision_id: str, expected_recording_fingerprint: str
) -> tuple[bytes, ...]:
    if not base.pin(expected_recording_fingerprint):
        raise Rejected("EXACT_EVIDENCE_SNAPSHOTS_SILVER_RECORDING_PIN_REQUIRED")
    base.readonly(reader)
    fingerprint, context = _read_recording(reader, revision_id=revision_id)
    if fingerprint != expected_recording_fingerprint:
        raise Rejected("EVIDENCE_SNAPSHOTS_SILVER_RECORDING_FINGERPRINT_CHANGED")
    rows = base.metadata(
        reader,
        f"SELECT ordinal,CASE WHEN octet_length(record_bytes)<=? THEN record_bytes END,"
        f"recorded_at FROM silver.silver.{OBSERVATIONS} WHERE revision_id=? ORDER BY ordinal",
        [MAX_RECORD, revision_id],
        -1,
    )
    records = tuple(bytes(row[1]) for row in rows)
    if not 1 <= len(records) <= 1000:
        raise Rejected("EVIDENCE_SNAPSHOTS_SILVER_ROW_BOUND")
    try:
        context_document = json.loads(context)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Rejected("EVIDENCE_SNAPSHOTS_SILVER_CONTEXT_RECORD_MISMATCH") from exc
    pins = context_document.get("pins") if isinstance(context_document, dict) else None
    if (
        not isinstance(context_document, dict)
        or set(context_document) != {"version", "pins", "record_hashes"}
        or context_document.get("version") != VERSION
        or not isinstance(pins, dict)
        or set(pins)
        != {
            "source_label",
            "snapshot_id",
            "capture_event_id",
            "envelope_hash",
            "recording_fingerprint",
        }
        or type(pins.get("source_label")) is not str
        or not all(
            base.pin(pins.get(key))
            for key in (
                "snapshot_id",
                "capture_event_id",
                "envelope_hash",
                "recording_fingerprint",
            )
        )
        or context_document.get("record_hashes") != [sha(record) for record in records]
        or base.canonical(context_document) != context
    ):
        raise Rejected("EVIDENCE_SNAPSHOTS_SILVER_CONTEXT_RECORD_MISMATCH")
    base.verify_recording(
        reader,
        command=COMMAND,
        scope_ref="sha256:" + scope_id(pins["source_label"]),
        config_hash=sha(context),
        revision_id=revision_id,
        sets_table=f"silver.silver.{SETS}",
        observations_table=f"silver.silver.{OBSERVATIONS}",
        attempts_table=f"silver.silver.{ATTEMPTS}",
        observation_count=len(records),
    )
    return records


def revalidate_evidence_snapshots_silver(
    bronze: Any,
    reader: Any,
    *,
    revision_id: str,
    expected_recording_fingerprint: str,
    source_label: str,
    snapshot_id: str,
    capture_event_id: str,
    envelope_hash: str,
    expected_bronze_recording_fingerprint: str,
) -> tuple[bytes, ...]:
    base.separate(bronze, reader)
    first = read_evidence_snapshots_silver(
        reader,
        revision_id=revision_id,
        expected_recording_fingerprint=expected_recording_fingerprint,
    )
    pins = EvidenceSnapshotBronzePins(
        source_label=source_label,
        snapshot_id=snapshot_id,
        capture_event_id=capture_event_id,
        envelope_hash=envelope_hash,
        recording_fingerprint=expected_bronze_recording_fingerprint,
    )
    context = observe_evidence_snapshots_bronze(bronze, pins=pins)
    _, recorded_context = _read_recording(reader, revision_id=revision_id)
    if context != recorded_context:
        raise Rejected("EVIDENCE_SNAPSHOTS_SILVER_REVALIDATION_MISMATCH")
    return first
