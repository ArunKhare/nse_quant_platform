"""Persisted materialized decision-evidence Silver over the actual Bronze reader."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from nse_quant.data_platform import legacy_decision_evidence as codec
from nse_quant.data_platform import legacy_decision_evidence_bronze as bronze_api
from nse_quant.data_platform import legacy_silver_common as base
from nse_quant.data_platform.audit import AuditLedger

VERSION = "legacy-decision-evidence-silver-materialized@1"
COMMAND = "normalize.legacy_decision_evidence@1"
TABLE = codec.TABLE
OBSERVATIONS = "decision_evidence_materialized_observations"
SETS = "decision_evidence_materialized_sets"
ATTEMPTS = "decision_evidence_materialized_attempts"
MAX_CONTEXT = 2200000
MAX_RECORD = codec.MAX_RECORD
MAX_RECORDS = codec.MAX_RECORDS
MAX_SCALAR = codec.MAX_CELL
MAX_SCALARS = 1048576
DEFINITION = (VERSION, COMMAND, "derived only from reviewed decision-evidence Bronze recording")


@dataclass(frozen=True)
class DecisionEvidenceBronzePins:
    source_label: str
    snapshot_id: str
    capture_event_id: str
    envelope_hash: str
    recording_fingerprint: str

    @property
    def scope_id(self) -> str:
        return codec.sha(codec.canonical([VERSION, self.source_label]))

    def reader_args(self) -> dict[str, str]:
        return dict(
            source_label=self.source_label,
            snapshot_id=self.snapshot_id,
            capture_event_id=self.capture_event_id,
            envelope_hash=self.envelope_hash,
            expected_recording_fingerprint=self.recording_fingerprint,
        )


def scope_id(source_label: str) -> str:
    return codec.sha(codec.canonical([VERSION, source_label]))


def initialize_decision_evidence_silver(target: Any) -> None:
    AuditLedger(target).initialize()
    target.execute("CREATE SCHEMA IF NOT EXISTS silver")
    target.execute(
        f"CREATE TABLE IF NOT EXISTS silver.{SETS} ("
        "revision_id VARCHAR PRIMARY KEY,context BLOB NOT NULL,"
        "context_sha256 VARCHAR NOT NULL,recorded_at TIMESTAMPTZ NOT NULL)"
    )
    target.execute(
        f"CREATE TABLE IF NOT EXISTS silver.{OBSERVATIONS} ("
        "revision_id VARCHAR NOT NULL,ordinal BIGINT NOT NULL,"
        "evidence_id VARCHAR NOT NULL,"
        "run_id VARCHAR NOT NULL,"
        "ts TIMESTAMP NOT NULL,"
        "symbol VARCHAR NOT NULL,"
        "plugin VARCHAR NOT NULL,"
        "available BOOLEAN,"
        "payload_json VARCHAR,"
        "record_bytes BLOB NOT NULL,recorded_at TIMESTAMPTZ NOT NULL,"
        "PRIMARY KEY(revision_id,ordinal),"
        "UNIQUE(revision_id,run_id,ts,symbol,plugin))"
    )
    target.execute(
        f"CREATE TABLE IF NOT EXISTS silver.{ATTEMPTS} ("
        "revision_id VARCHAR PRIMARY KEY,recorded_at TIMESTAMPTZ NOT NULL)"
    )


def observe_decision_evidence_bronze(bronze: Any, *, pins: DecisionEvidenceBronzePins) -> bytes:
    if not codec.pin(pins.recording_fingerprint):
        raise codec.Rejected("EXACT_DECISION_EVIDENCE_SILVER_BRONZE_PIN_REQUIRED")
    base.readonly(bronze)
    records = bronze_api.read_decision_evidence_bronze(bronze, **pins.reader_args())
    if not 1 <= len(records) <= codec.MAX_ROWS:
        raise codec.Rejected("DECISION_EVIDENCE_SILVER_ROW_BOUND")
    context = codec.canonical(
        dict(
            version=VERSION,
            pins={
                "source_label": pins.source_label,
                "snapshot_id": pins.snapshot_id,
                "capture_event_id": pins.capture_event_id,
                "envelope_hash": pins.envelope_hash,
                "recording_fingerprint": pins.recording_fingerprint,
            },
            record_hashes=[codec.sha(record) for record in records],
        )
    )
    if len(context) > MAX_CONTEXT:
        raise codec.Rejected("DECISION_EVIDENCE_SILVER_CONTEXT_BOUND")
    return context


def persist_decision_evidence_silver(
    bronze: Any,
    target: Any,
    *,
    pins: DecisionEvidenceBronzePins,
    expected_context_sha256: str,
    actor_id: str,
    code_revision: str,
) -> dict[str, Any]:
    if not codec.pin(expected_context_sha256) or not base.actor(actor_id) or not base.revision(code_revision):
        raise codec.Rejected("REVIEWED_DECISION_EVIDENCE_SILVER_REQUEST_REQUIRED")
    base.separate(bronze, target)
    base.readonly(bronze)
    revision_id = codec.sha(codec.canonical([VERSION, pins.scope_id, pins.capture_event_id, expected_context_sha256]))
    for table, field in ((f"silver.{SETS}", "revision_id"), (f"silver.{ATTEMPTS}", "revision_id")):
        if target.execute(f"SELECT 1 FROM {table} WHERE {field}=? LIMIT 1", [revision_id]).fetchone():
            raise codec.Rejected("DECISION_EVIDENCE_SILVER_FIRST_WRITE_ORIGINAL_OBLIGATION")
    ledger = AuditLedger(target)
    job = ledger.plan_job(
        command_name=COMMAND,
        actor_id=actor_id,
        code_revision=code_revision,
        scope_ref="sha256:" + scope_id(pins.source_label),
        config_hash=expected_context_sha256,
    )
    with ledger.execution(job):
        first = observe_decision_evidence_bronze(bronze, pins=pins)
        if codec.sha(first) != expected_context_sha256:
            raise codec.Rejected("REVIEWED_DECISION_EVIDENCE_BRONZE_CONTEXT_CHANGED")
        second = observe_decision_evidence_bronze(bronze, pins=pins)
        if second != first:
            raise codec.Rejected("DECISION_EVIDENCE_BRONZE_CONTEXT_DRIFT")
        records = bronze_api.read_decision_evidence_bronze(bronze, **pins.reader_args())
        materialized = []
        total_scalar = 0
        total_record = 0
        for ordinal, record in enumerate(records):
            if len(record) > MAX_RECORD:
                raise codec.Rejected("DECISION_EVIDENCE_SILVER_RECORD_BOUND")
            total_record += len(record)
            if total_record > MAX_RECORDS:
                raise codec.Rejected("DECISION_EVIDENCE_SILVER_AGGREGATE_BOUND")
            document = json.loads(record)
            fields = document["stored_fields"]
            evidence_id = fields["evidence_id"]
            run_id = fields["run_id"]
            ts = fields["ts"]
            symbol = fields["symbol"]
            plugin = fields["plugin"]
            if (
                type(evidence_id) is not str
                or not 0 < len(evidence_id.encode()) <= MAX_SCALAR
                or type(run_id) is not str
                or not 0 < len(run_id.encode()) <= MAX_SCALAR
                or type(ts) is not str
                or type(symbol) is not str
                or not 0 < len(symbol.encode()) <= MAX_SCALAR
                or type(plugin) is not str
                or not 0 < len(plugin.encode()) <= MAX_SCALAR
            ):
                raise codec.Rejected("DECISION_EVIDENCE_SILVER_KEY_REQUIRED")
            total_scalar += len(evidence_id.encode()) + len(run_id.encode())
            total_scalar += len(symbol.encode()) + len(plugin.encode())
            instant = datetime.fromisoformat(ts)
            if instant.tzinfo is not None:
                raise codec.Rejected("DECISION_EVIDENCE_SILVER_WALL_TS_REQUIRED")
            available = fields["available"]
            payload_json = fields["payload_json"]
            if type(available) is not bool:
                raise codec.Rejected("DECISION_EVIDENCE_SILVER_BOOLEAN_REQUIRED")
            if payload_json is not None:
                if type(payload_json) is not str:
                    raise codec.Rejected("DECISION_EVIDENCE_SILVER_TEXT_REQUIRED")
                size = len(payload_json.encode())
                if size > MAX_SCALAR:
                    raise codec.Rejected("DECISION_EVIDENCE_SILVER_SCALAR_BOUND")
                total_scalar += size
            if total_scalar > MAX_SCALARS:
                raise codec.Rejected("DECISION_EVIDENCE_SILVER_SCALAR_AGGREGATE_BOUND")
            materialized.append(
                (
                    ordinal,
                    evidence_id,
                    run_id,
                    instant,
                    symbol,
                    plugin,
                    available,
                    payload_json,
                    record,
                )
            )
        target.execute("BEGIN TRANSACTION")
        try:
            target.execute(
                f"INSERT INTO silver.{SETS} VALUES (?,?,?,?)",
                [revision_id, first, expected_context_sha256, base.clock(datetime.now(UTC))],
            )
            for row in materialized:
                target.execute(
                    f"INSERT INTO silver.{OBSERVATIONS} VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    [revision_id, *row, base.clock(datetime.now(UTC))],
                )
            target.execute(
                f"INSERT INTO silver.{ATTEMPTS} VALUES (?,?)",
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
    if not codec.pin(revision_id):
        raise codec.Rejected("EXACT_DECISION_EVIDENCE_SILVER_REVISION_PIN_REQUIRED")
    rows = base.metadata(
        target,
        f"SELECT CASE WHEN octet_length(context)<=? THEN to_hex(context) END,"
        f"CASE WHEN length(context_sha256)<=64 THEN context_sha256 END,recorded_at "
        f"FROM silver.{SETS} WHERE revision_id=?",
        [MAX_CONTEXT, revision_id],
        1,
    )
    context = bytes.fromhex(rows[0][0])
    if rows[0][1] != codec.sha(context):
        raise codec.Rejected("DECISION_EVIDENCE_SILVER_CONTEXT_HASH_MISMATCH")
    base.clock(rows[0][2])
    return codec.sha(codec.canonical([VERSION, revision_id, context.hex()])), context


def _materialized_values(record: bytes) -> tuple[object, ...]:
    document = json.loads(record)
    fields = document["stored_fields"]
    evidence_id = fields["evidence_id"]
    run_id = fields["run_id"]
    ts = fields["ts"]
    symbol = fields["symbol"]
    plugin = fields["plugin"]
    if (
        type(evidence_id) is not str
        or not 0 < len(evidence_id.encode()) <= MAX_SCALAR
        or type(run_id) is not str
        or not 0 < len(run_id.encode()) <= MAX_SCALAR
        or type(ts) is not str
        or type(symbol) is not str
        or not 0 < len(symbol.encode()) <= MAX_SCALAR
        or type(plugin) is not str
        or not 0 < len(plugin.encode()) <= MAX_SCALAR
    ):
        raise codec.Rejected("DECISION_EVIDENCE_SILVER_KEY_REQUIRED")
    instant = datetime.fromisoformat(ts)
    if instant.tzinfo is not None:
        raise codec.Rejected("DECISION_EVIDENCE_SILVER_WALL_TS_REQUIRED")
    available = fields["available"]
    payload_json = fields["payload_json"]
    if available is not None and type(available) is not bool:
        raise codec.Rejected("DECISION_EVIDENCE_SILVER_BOOLEAN_REQUIRED")
    if payload_json is not None and type(payload_json) is not str:
        raise codec.Rejected("DECISION_EVIDENCE_SILVER_TEXT_REQUIRED")
    return (evidence_id, run_id, instant, symbol, plugin, available, payload_json)


def read_decision_evidence_silver(
    reader: Any, *, revision_id: str, expected_recording_fingerprint: str
) -> tuple[bytes, ...]:
    if not codec.pin(expected_recording_fingerprint):
        raise codec.Rejected("EXACT_DECISION_EVIDENCE_SILVER_RECORDING_PIN_REQUIRED")
    base.readonly(reader)
    fingerprint, context = _read_recording(reader, revision_id=revision_id)
    if fingerprint != expected_recording_fingerprint:
        raise codec.Rejected("DECISION_EVIDENCE_SILVER_RECORDING_FINGERPRINT_CHANGED")
    text_fields = ("evidence_id", "run_id", "symbol", "plugin", "payload_json")
    guards = []
    sizes = []
    overflow = []
    for name in text_fields:
        quoted = '"' + name + '"'
        length = f"octet_length(encode({quoted}))"
        guards.append(f"CASE WHEN {length}<={MAX_SCALAR} THEN {quoted} END")
        sizes.append(f"coalesce({length},0)")
        overflow.append(f"coalesce({length}>{MAX_SCALAR},false)")
    guards += ['"ts"', '"available"']
    guards += [
        "CASE WHEN octet_length(record_bytes)<=? THEN record_bytes END",
        "recorded_at",
    ]
    columns = ",".join(["ordinal", *guards])
    totals_sql = (
        "SELECT count(*),coalesce(sum(octet_length(record_bytes)),0),"
        "coalesce(max(octet_length(record_bytes)),0),"
        f"coalesce(sum({'+'.join(sizes)}),0),"
        f"coalesce(bool_or({' OR '.join(overflow)}),false) "
        f"FROM silver.{OBSERVATIONS} WHERE revision_id=?"
    )
    totals = base.metadata(reader, totals_sql, [revision_id], 1)[0]
    if (
        totals[0] < 1
        or totals[0] > codec.MAX_ROWS
        or totals[1] > MAX_RECORDS
        or totals[2] > MAX_RECORD
        or totals[3] > MAX_SCALARS
        or totals[4]
    ):
        raise codec.Rejected("DECISION_EVIDENCE_SILVER_TRANSFER_BOUND")
    rows = base.metadata(
        reader,
        f"SELECT {columns} FROM silver.{OBSERVATIONS} WHERE revision_id=? ORDER BY ordinal LIMIT ?",
        [MAX_RECORD, revision_id, codec.MAX_ROWS + 1],
        -1,
    )
    if len(rows) != totals[0]:
        raise codec.Rejected("DECISION_EVIDENCE_SILVER_ROW_BOUND")
    records = tuple(bytes(row[8]) for row in rows)
    if [row[0] for row in rows] != list(range(len(rows))):
        raise codec.Rejected("DECISION_EVIDENCE_SILVER_ORDINAL_COVERAGE_MISMATCH")
    try:
        context_document = json.loads(context)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise codec.Rejected("DECISION_EVIDENCE_SILVER_CONTEXT_RECORD_MISMATCH") from exc
    expected_hashes = [codec.sha(record) for record in records]
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
            codec.pin(pins.get(key))
            for key in ("snapshot_id", "capture_event_id", "envelope_hash", "recording_fingerprint")
        )
        or context_document.get("record_hashes") != expected_hashes
        or codec.canonical(context_document) != context
    ):
        raise codec.Rejected("DECISION_EVIDENCE_SILVER_CONTEXT_RECORD_MISMATCH")
    for row, record in zip(rows, records, strict=True):
        expected = _materialized_values(record)
        actual = (row[1], row[2], row[6], row[3], row[4], row[7], row[5])
        if actual != expected:
            raise codec.Rejected("DECISION_EVIDENCE_SILVER_MATERIALIZED_FIELD_MISMATCH")
    base.verify_recording(
        reader,
        command=COMMAND,
        scope_ref="sha256:" + scope_id(pins["source_label"]),
        config_hash=codec.sha(context),
        revision_id=revision_id,
        sets_table=f"silver.{SETS}",
        observations_table=f"silver.{OBSERVATIONS}",
        attempts_table=f"silver.{ATTEMPTS}",
        observation_count=len(records),
    )
    return records


def revalidate_decision_evidence_silver(
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
    first = read_decision_evidence_silver(
        reader,
        revision_id=revision_id,
        expected_recording_fingerprint=expected_recording_fingerprint,
    )
    pins = DecisionEvidenceBronzePins(
        source_label=source_label,
        snapshot_id=snapshot_id,
        capture_event_id=capture_event_id,
        envelope_hash=envelope_hash,
        recording_fingerprint=expected_bronze_recording_fingerprint,
    )
    context = observe_decision_evidence_bronze(bronze, pins=pins)
    _, recorded_context = _read_recording(reader, revision_id=revision_id)
    if context != recorded_context:
        raise codec.Rejected("DECISION_EVIDENCE_SILVER_REVALIDATION_MISMATCH")
    return first
