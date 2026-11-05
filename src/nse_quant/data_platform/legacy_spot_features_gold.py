"""Persisted spot-features Gold derived only from the reviewed Silver recording."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from nse_quant.data_platform import legacy_silver_common as base
from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.legacy_spot_features import Rejected, sha
from nse_quant.data_platform.legacy_spot_features_silver import (
    read_spot_features_silver,
)

VERSION = "legacy-spot-features-gold-recording@1"
COMMAND = "persist.legacy_spot_features_gold@1"
TABLE = "spot_features"
OBSERVATIONS = "spot_feature_gold_observations"
SETS = "spot_feature_gold_sets"
ATTEMPTS = "spot_feature_gold_attempts"
MAX_CONTEXT = 1048576
DEFINITION = (VERSION, COMMAND, "derived only from reviewed spot-features Silver recording")


def scope_id(source_label: str) -> str:
    return base.sha(base.canonical([VERSION, source_label]))


def initialize_spot_features_gold(target: Any) -> None:
    AuditLedger(target).initialize()
    target.execute("CREATE SCHEMA IF NOT EXISTS gold")
    target.execute(
        f"CREATE TABLE IF NOT EXISTS gold.{SETS} ("
        "revision_id VARCHAR PRIMARY KEY,context BLOB NOT NULL,"
        "context_sha256 VARCHAR NOT NULL,recorded_at TIMESTAMPTZ NOT NULL)"
    )
    target.execute(
        f"CREATE TABLE IF NOT EXISTS gold.{OBSERVATIONS} ("
        "revision_id VARCHAR NOT NULL,ordinal BIGINT NOT NULL,"
        "record_bytes BLOB NOT NULL,recorded_at TIMESTAMPTZ NOT NULL,"
        "PRIMARY KEY(revision_id,ordinal))"
    )
    target.execute(
        f"CREATE TABLE IF NOT EXISTS gold.{ATTEMPTS} ("
        "revision_id VARCHAR PRIMARY KEY,recorded_at TIMESTAMPTZ NOT NULL)"
    )


def observe_spot_features_silver(
    silver: Any,
    *,
    pins: base.SilverPins,
    revision_id: str,
    expected_silver_recording_fingerprint: str,
) -> bytes:
    if not base.pin(expected_silver_recording_fingerprint) or not base.pin(revision_id):
        raise Rejected("EXACT_SPOT_FEATURES_GOLD_SILVER_PIN_REQUIRED")
    base.readonly(silver)
    records = read_spot_features_silver(
        silver,
        revision_id=revision_id,
        expected_recording_fingerprint=expected_silver_recording_fingerprint,
    )
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
            silver_revision_id=revision_id,
            silver_recording_fingerprint=expected_silver_recording_fingerprint,
            record_hashes=[sha(record) for record in records],
        )
    )
    if len(context) > MAX_CONTEXT:
        raise Rejected("SPOT_FEATURES_GOLD_CONTEXT_BOUND")
    return context


def persist_spot_features_gold(
    silver: Any,
    target: Any,
    *,
    pins: base.SilverPins,
    silver_revision_id: str,
    expected_silver_recording_fingerprint: str,
    expected_context_sha256: str,
    actor_id: str,
    code_revision: str,
) -> dict[str, Any]:
    if (
        not base.pin(expected_context_sha256)
        or not base.pin(expected_silver_recording_fingerprint)
        or not base.actor(actor_id)
        or not base.revision(code_revision)
    ):
        raise Rejected("REVIEWED_SPOT_FEATURES_GOLD_REQUEST_REQUIRED")
    base.separate(silver, target)
    base.readonly(silver)
    revision_id = base.sha(
        base.canonical(
            [
                VERSION,
                pins.recording_fingerprint,
                silver_revision_id,
                expected_silver_recording_fingerprint,
                expected_context_sha256,
            ]
        )
    )
    for table, field in ((f"gold.{SETS}", "revision_id"), (f"gold.{ATTEMPTS}", "revision_id")):
        if target.execute(
            f"SELECT 1 FROM {table} WHERE {field}=? LIMIT 1", [revision_id]
        ).fetchone():
            raise Rejected("SPOT_FEATURES_GOLD_FIRST_WRITE_ORIGINAL_OBLIGATION")
    ledger = AuditLedger(target)
    job = ledger.plan_job(
        command_name=COMMAND,
        actor_id=actor_id,
        code_revision=code_revision,
        scope_ref="sha256:" + scope_id(pins.source_label),
        config_hash=expected_context_sha256,
    )
    with ledger.execution(job):
        first = observe_spot_features_silver(
            silver,
            pins=pins,
            revision_id=silver_revision_id,
            expected_silver_recording_fingerprint=expected_silver_recording_fingerprint,
        )
        if sha(first) != expected_context_sha256:
            raise Rejected("REVIEWED_SPOT_FEATURES_SILVER_CONTEXT_CHANGED")
        second = observe_spot_features_silver(
            silver,
            pins=pins,
            revision_id=silver_revision_id,
            expected_silver_recording_fingerprint=expected_silver_recording_fingerprint,
        )
        if second != first:
            raise Rejected("SPOT_FEATURES_SILVER_CONTEXT_DRIFT")
        records = read_spot_features_silver(
            silver,
            revision_id=silver_revision_id,
            expected_recording_fingerprint=expected_silver_recording_fingerprint,
        )
        target.execute("BEGIN TRANSACTION")
        try:
            target.execute(
                f"INSERT INTO gold.{SETS} VALUES (?,?,?,?)",
                [revision_id, first, expected_context_sha256, base.clock(datetime.now(UTC))],
            )
            for ordinal, record in enumerate(records):
                target.execute(
                    f"INSERT INTO gold.{OBSERVATIONS} VALUES (?,?,?,?)",
                    [revision_id, ordinal, record, base.clock(datetime.now(UTC))],
                )
            target.execute(
                f"INSERT INTO gold.{ATTEMPTS} VALUES (?,?)",
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
        raise Rejected("EXACT_SPOT_FEATURES_GOLD_REVISION_PIN_REQUIRED")
    rows = base.metadata(
        target,
        f"SELECT CASE WHEN octet_length(context)<=? THEN context END,"
        f"CASE WHEN length(context_sha256)<=64 THEN context_sha256 END,recorded_at "
        f"FROM gold.{SETS} WHERE revision_id=?",
        [MAX_CONTEXT, revision_id],
        1,
    )
    context = bytes(rows[0][0])
    if rows[0][1] != sha(context):
        raise Rejected("SPOT_FEATURES_GOLD_CONTEXT_HASH_MISMATCH")
    base.clock(rows[0][2])
    return sha(base.canonical([VERSION, revision_id, context.hex()])), context


def read_spot_features_gold(
    reader: Any, *, revision_id: str, expected_recording_fingerprint: str
) -> tuple[bytes, ...]:
    if not base.pin(expected_recording_fingerprint):
        raise Rejected("EXACT_SPOT_FEATURES_GOLD_RECORDING_PIN_REQUIRED")
    base.readonly(reader)
    fingerprint, context = _read_recording(reader, revision_id=revision_id)
    if fingerprint != expected_recording_fingerprint:
        raise Rejected("SPOT_FEATURES_GOLD_RECORDING_FINGERPRINT_CHANGED")
    rows = base.metadata(
        reader,
        f"SELECT ordinal,CASE WHEN octet_length(record_bytes)<=1048576 THEN record_bytes END,"
        f"recorded_at FROM gold.{OBSERVATIONS} WHERE revision_id=? ORDER BY ordinal",
        [revision_id],
        -1,
    )
    records = tuple(bytes(row[1]) for row in rows)
    try:
        context_document = json.loads(context)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Rejected("SPOT_FEATURES_GOLD_CONTEXT_RECORD_MISMATCH") from exc
    expected_context = dict(
        version=VERSION,
        pins=context_document.get("pins") if isinstance(context_document, dict) else None,
        silver_revision_id=context_document.get("silver_revision_id")
        if isinstance(context_document, dict)
        else None,
        silver_recording_fingerprint=context_document.get("silver_recording_fingerprint")
        if isinstance(context_document, dict)
        else None,
        record_hashes=[sha(record) for record in records],
    )
    if (
        not isinstance(context_document, dict)
        or set(context_document) != set(expected_context)
        or context_document.get("version") != VERSION
        or not isinstance(context_document.get("pins"), dict)
        or type(context_document["pins"].get("source_label")) is not str
        or not base.pin(context_document.get("silver_revision_id"))
        or not base.pin(context_document.get("silver_recording_fingerprint"))
        or context_document.get("record_hashes") != expected_context["record_hashes"]
        or base.canonical(context_document) != context
    ):
        raise Rejected("SPOT_FEATURES_GOLD_CONTEXT_RECORD_MISMATCH")
    base.verify_recording(
        reader,
        command=COMMAND,
        scope_ref="sha256:" + scope_id(context_document["pins"]["source_label"]),
        config_hash=sha(context),
        revision_id=revision_id,
        sets_table=f"gold.{SETS}",
        observations_table=f"gold.{OBSERVATIONS}",
        attempts_table=f"gold.{ATTEMPTS}",
        observation_count=len(records),
    )
    return records


def revalidate_spot_features_gold(silver: Any, reader: Any, **args: Any) -> tuple[bytes, ...]:
    base.separate(silver, reader)
    first = read_spot_features_gold(
        reader,
        revision_id=args["revision_id"],
        expected_recording_fingerprint=args["expected_recording_fingerprint"],
    )
    pins = base.SilverPins(
        source_label=args.get("source_label", ""),
        snapshot_id=args.get("snapshot_id", ""),
        capture_event_id=args.get("capture_event_id", ""),
        envelope_hash=args.get("envelope_hash", ""),
        recording_fingerprint=args.get("recording_fingerprint", ""),
    )
    context = observe_spot_features_silver(
        silver,
        pins=pins,
        revision_id=args["silver_revision_id"],
        expected_silver_recording_fingerprint=args["expected_silver_recording_fingerprint"],
    )
    _, recorded_context = _read_recording(reader, revision_id=args["revision_id"])
    if context != recorded_context:
        raise Rejected("SPOT_FEATURES_GOLD_REVALIDATION_MISMATCH")
    return first
