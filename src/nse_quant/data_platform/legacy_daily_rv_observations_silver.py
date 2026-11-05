"""Persisted daily-RV Silver derived only from the new Bronze recording."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from nse_quant.data_platform import legacy_silver_common as base
from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.bronze import BronzeEventStore
from nse_quant.data_platform.legacy_daily_rv_observations import Rejected, sha
from nse_quant.data_platform.legacy_daily_rv_observations_bronze import (
    read_daily_rv_observations_bronze,
)

VERSION = "legacy-daily-rv-observations-silver-recording@1"
COMMAND = "persist.legacy_daily_rv_observations_silver@1"
TABLE = "daily_rv_observations"
OBSERVATIONS = "daily_rv_observations"
SETS = "daily_rv_sets"
ATTEMPTS = "daily_rv_attempts"
MAX_CONTEXT = 1048576
DEFINITION = (VERSION, COMMAND, "derived only from reviewed daily-RV Bronze recording")


def scope_id(source_label: str) -> str:
    return base.sha(base.canonical([VERSION, source_label]))


def initialize_daily_rv_silver(target: Any) -> None:
    target.execute("CREATE SCHEMA IF NOT EXISTS silver")
    target.execute(
        f"CREATE TABLE IF NOT EXISTS silver.{SETS} ("
        "revision_id VARCHAR PRIMARY KEY,context BLOB NOT NULL,"
        "context_sha256 VARCHAR NOT NULL,recorded_at TIMESTAMPTZ NOT NULL)"
    )
    target.execute(
        f"CREATE TABLE IF NOT EXISTS silver.{OBSERVATIONS} ("
        "revision_id VARCHAR NOT NULL,ordinal BIGINT NOT NULL,"
        "record_bytes BLOB NOT NULL,recorded_at TIMESTAMPTZ NOT NULL,"
        "PRIMARY KEY(revision_id,ordinal))"
    )
    target.execute(
        f"CREATE TABLE IF NOT EXISTS silver.{ATTEMPTS} ("
        "revision_id VARCHAR PRIMARY KEY,recorded_at TIMESTAMPTZ NOT NULL)"
    )


def observe_daily_rv_bronze(bronze: Any, *, pins: base.SilverPins) -> bytes:
    if not base.pin(pins.recording_fingerprint):
        raise Rejected("EXACT_DAILY_RV_SILVER_BRONZE_PIN_REQUIRED")
    base.readonly(bronze)
    records = read_daily_rv_observations_bronze(bronze, **pins.reader_args())
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
        raise Rejected("DAILY_RV_SILVER_CONTEXT_BOUND")
    return context


def persist_daily_rv_silver(
    bronze: Any,
    target: Any,
    *,
    pins: base.SilverPins,
    expected_context_sha256: str,
    actor_id: str,
    code_revision: str,
) -> dict[str, Any]:
    if (
        not base.pin(expected_context_sha256)
        or not base.actor(actor_id)
        or not base.revision(code_revision)
    ):
        raise Rejected("REVIEWED_DAILY_RV_SILVER_REQUEST_REQUIRED")
    base.separate(bronze, target)
    base.readonly(bronze)
    store = BronzeEventStore(target)
    store.verify_target()
    revision_id = base.sha(
        base.canonical([VERSION, pins.recording_fingerprint, expected_context_sha256])
    )
    for table, field in ((f"silver.{SETS}", "revision_id"), (f"silver.{ATTEMPTS}", "revision_id")):
        if target.execute(
            f"SELECT 1 FROM {table} WHERE {field}=? LIMIT 1", [revision_id]
        ).fetchone():
            raise Rejected("DAILY_RV_SILVER_FIRST_WRITE_ORIGINAL_OBLIGATION")
    ledger = AuditLedger(target)
    job = ledger.plan_job(
        command_name=COMMAND,
        actor_id=actor_id,
        code_revision=code_revision,
        scope_ref="sha256:" + scope_id(pins.source_label),
        config_hash=expected_context_sha256,
    )
    with ledger.execution(job):
        first = observe_daily_rv_bronze(bronze, pins=pins)
        if sha(first) != expected_context_sha256:
            raise Rejected("REVIEWED_DAILY_RV_BRONZE_CONTEXT_CHANGED")
        second = observe_daily_rv_bronze(bronze, pins=pins)
        if second != first:
            raise Rejected("DAILY_RV_BRONZE_CONTEXT_DRIFT")
        records = read_daily_rv_observations_bronze(bronze, **pins.reader_args())
        target.execute("BEGIN TRANSACTION")
        try:
            target.execute(
                f"INSERT INTO silver.{SETS} VALUES (?,?,?,?)",
                [revision_id, first, expected_context_sha256, base.clock(datetime.now())],
            )
            for ordinal, record in enumerate(records):
                target.execute(
                    f"INSERT INTO silver.{OBSERVATIONS} VALUES (?,?,?,?)",
                    [revision_id, ordinal, record, base.clock(datetime.now())],
                )
            target.execute(
                f"INSERT INTO silver.{ATTEMPTS} VALUES (?,?)",
                [revision_id, base.clock(datetime.now())],
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
        raise Rejected("EXACT_DAILY_RV_SILVER_REVISION_PIN_REQUIRED")
    rows = base.metadata(
        target,
        f"SELECT CASE WHEN octet_length(context)<=? THEN context END,"
        f"CASE WHEN length(context_sha256)<=64 THEN context_sha256 END,recorded_at "
        f"FROM silver.{SETS} WHERE revision_id=?",
        [MAX_CONTEXT, revision_id],
        1,
    )
    context = bytes(rows[0][0])
    if rows[0][1] != sha(context):
        raise Rejected("DAILY_RV_SILVER_CONTEXT_HASH_MISMATCH")
    base.clock(rows[0][2])
    return sha(base.canonical([VERSION, revision_id, context])), context


def read_daily_rv_silver(
    reader: Any, *, revision_id: str, expected_recording_fingerprint: str
) -> tuple[bytes, ...]:
    if not base.pin(expected_recording_fingerprint):
        raise Rejected("EXACT_DAILY_RV_SILVER_RECORDING_PIN_REQUIRED")
    base.readonly(reader)
    fingerprint, context = _read_recording(reader, revision_id=revision_id)
    if fingerprint != expected_recording_fingerprint:
        raise Rejected("DAILY_RV_SILVER_RECORDING_FINGERPRINT_CHANGED")
    rows = base.metadata(
        reader,
        f"SELECT ordinal,CASE WHEN octet_length(record_bytes)<=1048576 THEN record_bytes END,"
        f"recorded_at FROM silver.{OBSERVATIONS} WHERE revision_id=? ORDER BY ordinal",
        [revision_id],
        -1,
    )
    records = tuple(bytes(row[1]) for row in rows)
    document = base.canonical(
        dict(
            version=VERSION,
            revision_id=revision_id,
            context_sha256=sha(context),
            record_hashes=[sha(record) for record in records],
        )
    )
    if sha(document) != sha(context):
        raise Rejected("DAILY_RV_SILVER_CONTEXT_RECORD_MISMATCH")
    return records


def revalidate_daily_rv_silver(bronze: Any, reader: Any, **args: Any) -> tuple[bytes, ...]:
    base.separate(bronze, reader)
    first = read_daily_rv_silver(reader, **args)
    pins = base.SilverPins(
        source_label=args.get("source_label", ""),
        snapshot_id=args.get("snapshot_id", ""),
        capture_event_id=args.get("capture_event_id", ""),
        envelope_hash=args.get("envelope_hash", ""),
        recording_fingerprint=args.get("expected_recording_fingerprint", ""),
    )
    context = observe_daily_rv_bronze(bronze, pins=pins)
    if sha(context) != sha(
        first
        and base.canonical(
            dict(
                version=VERSION,
                revision_id=args["revision_id"],
                context_sha256=sha(context),
                record_hashes=[sha(r) for r in first],
            )
        )
    ):
        raise Rejected("DAILY_RV_SILVER_REVALIDATION_MISMATCH")
    return first
