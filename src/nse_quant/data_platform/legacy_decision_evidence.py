"""Decision-evidence layer derived only from the reviewed market Gold bundle."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from nse_quant.data_platform import legacy_market_gold_bundle as bundle
from nse_quant.data_platform import legacy_silver_common as base
from nse_quant.data_platform.audit import AuditLedger
from nse_quant.data_platform.legacy_spot_candles import Rejected, sha

VERSION = "legacy-decision-evidence-recording@1"
COMMAND = "persist.legacy_decision_evidence@1"
TABLE = "decision_evidence"
OBSERVATIONS = "decision_evidence_observations"
SETS = "decision_evidence_sets"
ATTEMPTS = "decision_evidence_attempts"
MAX_CONTEXT = 1048576
MEMBERS = bundle.MEMBERS
DEFINITION = (
    VERSION,
    COMMAND,
    "derived only from the reviewed market Gold bundle; no eligibility granted",
)


def scope_id(source_label: str) -> str:
    return base.sha(base.canonical([VERSION, source_label]))


def initialize_decision_evidence(target: Any) -> None:
    AuditLedger(target).initialize()
    target.execute("CREATE SCHEMA IF NOT EXISTS gold")
    target.execute(
        f"CREATE TABLE IF NOT EXISTS gold.{SETS} ("
        "revision_id VARCHAR PRIMARY KEY,context BLOB NOT NULL,"
        "context_sha256 VARCHAR NOT NULL,recorded_at TIMESTAMPTZ NOT NULL)"
    )
    target.execute(
        f"CREATE TABLE IF NOT EXISTS gold.{OBSERVATIONS} ("
        "revision_id VARCHAR NOT NULL,member VARCHAR NOT NULL,ordinal BIGINT NOT NULL,"
        "record_bytes BLOB NOT NULL,recorded_at TIMESTAMPTZ NOT NULL,"
        "PRIMARY KEY(revision_id,member,ordinal))"
    )
    target.execute(
        f"CREATE TABLE IF NOT EXISTS gold.{ATTEMPTS} ("
        "revision_id VARCHAR PRIMARY KEY,recorded_at TIMESTAMPTZ NOT NULL)"
    )


def observe_decision_evidence_bundle(
    bundle_reader: Any, *, pins: base.SilverPins, bundle_revision_id: str
) -> bytes:
    if not base.pin(pins.recording_fingerprint) or not base.pin(bundle_revision_id):
        raise Rejected("EXACT_DECISION_EVIDENCE_BUNDLE_PIN_REQUIRED")
    base.readonly(bundle_reader)
    members = bundle.read_market_gold_bundle(
        bundle_reader,
        revision_id=bundle_revision_id,
        expected_recording_fingerprint=pins.recording_fingerprint,
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
            bundle_revision_id=bundle_revision_id,
            record_hashes={
                name: [sha(record) for record in records] for name, records in members.items()
            },
        )
    )
    if len(context) > MAX_CONTEXT:
        raise Rejected("DECISION_EVIDENCE_CONTEXT_BOUND")
    return context


def persist_decision_evidence(
    bundle_reader: Any,
    target: Any,
    *,
    pins: base.SilverPins,
    bundle_revision_id: str,
    expected_context_sha256: str,
    actor_id: str,
    code_revision: str,
) -> dict[str, Any]:
    if (
        not base.pin(expected_context_sha256)
        or not base.actor(actor_id)
        or not base.revision(code_revision)
    ):
        raise Rejected("REVIEWED_DECISION_EVIDENCE_REQUEST_REQUIRED")
    base.separate(bundle_reader, target)
    base.readonly(bundle_reader)
    revision_id = base.sha(
        base.canonical(
            [VERSION, pins.recording_fingerprint, bundle_revision_id, expected_context_sha256]
        )
    )
    for table, field in ((f"gold.{SETS}", "revision_id"), (f"gold.{ATTEMPTS}", "revision_id")):
        if target.execute(
            f"SELECT 1 FROM {table} WHERE {field}=? LIMIT 1", [revision_id]
        ).fetchone():
            raise Rejected("DECISION_EVIDENCE_FIRST_WRITE_ORIGINAL_OBLIGATION")
    ledger = AuditLedger(target)
    job = ledger.plan_job(
        command_name=COMMAND,
        actor_id=actor_id,
        code_revision=code_revision,
        scope_ref="sha256:" + scope_id(pins.source_label),
        config_hash=expected_context_sha256,
    )
    with ledger.execution(job):
        first = observe_decision_evidence_bundle(
            bundle_reader, pins=pins, bundle_revision_id=bundle_revision_id
        )
        if sha(first) != expected_context_sha256:
            raise Rejected("REVIEWED_DECISION_EVIDENCE_CONTEXT_CHANGED")
        second = observe_decision_evidence_bundle(
            bundle_reader, pins=pins, bundle_revision_id=bundle_revision_id
        )
        if second != first:
            raise Rejected("DECISION_EVIDENCE_CONTEXT_DRIFT")
        members = bundle.read_market_gold_bundle(
            bundle_reader,
            revision_id=bundle_revision_id,
            expected_recording_fingerprint=pins.recording_fingerprint,
        )
        target.execute("BEGIN TRANSACTION")
        try:
            target.execute(
                f"INSERT INTO gold.{SETS} VALUES (?,?,?,?)",
                [revision_id, first, expected_context_sha256, base.clock(datetime.now(UTC))],
            )
            for member, records in members.items():
                for ordinal, record in enumerate(records):
                    target.execute(
                        f"INSERT INTO gold.{OBSERVATIONS} VALUES (?,?,?,?,?)",
                        [revision_id, member, ordinal, record, base.clock(datetime.now(UTC))],
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
        row_count=sum(len(records) for records in members.values()),
        job_id=job,
        decision_eligibility_asserted=False,
    )


def _read_recording(target: Any, *, revision_id: str) -> tuple[str, bytes]:
    if not base.pin(revision_id):
        raise Rejected("EXACT_DECISION_EVIDENCE_REVISION_PIN_REQUIRED")
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
        raise Rejected("DECISION_EVIDENCE_CONTEXT_HASH_MISMATCH")
    base.clock(rows[0][2])
    return sha(base.canonical([VERSION, revision_id, context.hex()])), context


def read_decision_evidence(
    reader: Any, *, revision_id: str, expected_recording_fingerprint: str
) -> dict[str, tuple[bytes, ...]]:
    if not base.pin(expected_recording_fingerprint):
        raise Rejected("EXACT_DECISION_EVIDENCE_RECORDING_PIN_REQUIRED")
    base.readonly(reader)
    fingerprint, context = _read_recording(reader, revision_id=revision_id)
    if fingerprint != expected_recording_fingerprint:
        raise Rejected("DECISION_EVIDENCE_RECORDING_FINGERPRINT_CHANGED")
    rows = base.metadata(
        reader,
        "SELECT member,ordinal,"
        "CASE WHEN octet_length(record_bytes)<=1048576 THEN record_bytes END,"
        f"recorded_at FROM gold.{OBSERVATIONS} WHERE revision_id=? ORDER BY member,ordinal",
        [revision_id],
        -1,
    )
    members: dict[str, list[bytes]] = {name: [] for name in MEMBERS}
    for row in rows:
        if row[0] not in members:
            raise Rejected("DECISION_EVIDENCE_MEMBER_COVERAGE_MISMATCH")
        members[row[0]].append(bytes(row[2]))
    try:
        context_document = json.loads(context)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Rejected("DECISION_EVIDENCE_CONTEXT_RECORD_MISMATCH") from exc
    expected_hashes = {
        name: [sha(record) for record in records] for name, records in members.items()
    }
    if (
        not isinstance(context_document, dict)
        or set(context_document) != {"version", "pins", "bundle_revision_id", "record_hashes"}
        or context_document.get("version") != VERSION
        or not isinstance(context_document.get("pins"), dict)
        or type(context_document["pins"].get("source_label")) is not str
        or not base.pin(context_document.get("bundle_revision_id"))
        or context_document.get("record_hashes") != expected_hashes
        or base.canonical(context_document) != context
    ):
        raise Rejected("DECISION_EVIDENCE_CONTEXT_RECORD_MISMATCH")
    base.verify_recording(
        reader,
        command=COMMAND,
        scope_ref="sha256:" + scope_id(context_document["pins"]["source_label"]),
        config_hash=sha(context),
        revision_id=revision_id,
        sets_table=f"gold.{SETS}",
        observations_table=f"gold.{OBSERVATIONS}",
        attempts_table=f"gold.{ATTEMPTS}",
        observation_count=sum(len(records) for records in members.values()),
    )
    return {name: tuple(records) for name, records in members.items()}


def revalidate_decision_evidence(
    bundle_reader: Any, reader: Any, **args: Any
) -> dict[str, tuple[bytes, ...]]:
    base.separate(bundle_reader, reader)
    first = read_decision_evidence(
        reader,
        revision_id=args["revision_id"],
        expected_recording_fingerprint=args["expected_recording_fingerprint"],
    )
    pins = base.SilverPins(
        source_label=args.get("source_label", ""),
        snapshot_id=args.get("snapshot_id", ""),
        capture_event_id=args.get("capture_event_id", ""),
        envelope_hash=args.get("envelope_hash", ""),
        recording_fingerprint=args["bundle_recording_fingerprint"],
    )
    context = observe_decision_evidence_bundle(
        bundle_reader, pins=pins, bundle_revision_id=args["bundle_revision_id"]
    )
    _, recorded_context = _read_recording(reader, revision_id=args["revision_id"])
    if context != recorded_context:
        raise Rejected("DECISION_EVIDENCE_REVALIDATION_MISMATCH")
    return first
