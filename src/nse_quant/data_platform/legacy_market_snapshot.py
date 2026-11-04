"""Bounded legacy SQL snapshots through native Bronze; no production migration CLI."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

VERSION = "legacy-market-snapshot@1"
MAX_ROWS = 1000
MAX_CELL = 65536
MAX_BYTES = 1048576
COMMAND = "migrate.legacy_market_snapshot@1"
SCHEMAS = {
    "option_stream": tuple(
        zip(
            (
                "run_id",
                "ts",
                "underlying",
                "expiry",
                "strike",
                "option_type",
                "tradingsymbol",
                "instrument_token",
                "lot_size",
                "spot",
                "ltp",
                "bid",
                "ask",
                "volume",
                "oi",
                "iv",
                "delta",
                "gamma",
                "vega",
                "theta",
                "quote_status",
                "payload_json",
            ),
            (
                "VARCHAR",
                "TIMESTAMP WITH TIME ZONE",
                "VARCHAR",
                "DATE",
                "DOUBLE",
                "VARCHAR",
                "VARCHAR",
                "BIGINT",
                "INTEGER",
                "DOUBLE",
                "DOUBLE",
                "DOUBLE",
                "DOUBLE",
                "BIGINT",
                "BIGINT",
                "DOUBLE",
                "DOUBLE",
                "DOUBLE",
                "DOUBLE",
                "DOUBLE",
                "VARCHAR",
                "JSON",
            ),
            strict=True,
        )
    ),
    "spot_candles": tuple(
        zip(
            (
                "instrument_token",
                "symbol",
                "interval",
                "ts",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "oi",
            ),
            (
                "BIGINT",
                "VARCHAR",
                "VARCHAR",
                "TIMESTAMP WITH TIME ZONE",
                "DOUBLE",
                "DOUBLE",
                "DOUBLE",
                "DOUBLE",
                "BIGINT",
                "BIGINT",
            ),
            strict=True,
        )
    ),
}
KEYS = {"option_stream": (0, 1, 7), "spot_candles": (0, 2, 3)}
DERIVED = frozenset(("iv", "delta", "gamma", "vega", "theta"))


class MigrationRejected(ValueError):
    """Fixed diagnostic codes; operational failures propagate."""


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _pin(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _quote(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _name(conn: Any, schema: str, table: str) -> str:
    row = conn.execute("SELECT current_database()").fetchone()
    if row is None:
        raise MigrationRejected("CATALOG_UNAVAILABLE")
    return ".".join(_quote(str(x)) for x in (row[0], schema, table))


def _cell(value: object, kind: str) -> object:
    if value is None:
        return None
    if kind == "DOUBLE":
        if type(value) is not float or not math.isfinite(value):
            raise MigrationRejected("FINITE_BINARY64_REQUIRED")
        return value.hex()
    if kind in ("INTEGER", "BIGINT"):
        if type(value) is not int:
            raise MigrationRejected("EXACT_INTEGER_REQUIRED")
        return str(value)
    if kind == "TIMESTAMP WITH TIME ZONE":
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise MigrationRejected("AWARE_STORED_TIMESTAMP_REQUIRED")
        return value.astimezone(UTC).isoformat()
    if kind == "DATE":
        if type(value) is not date:
            raise MigrationRejected("EXACT_DATE_REQUIRED")
        return value.isoformat()
    if type(value) is not str or len(value.encode()) > MAX_CELL:
        raise MigrationRejected("TEXT_CELL_BOUND")
    return value


@dataclass(frozen=True)
class LegacySnapshot:
    snapshot_id: str
    payload: bytes
    row_count: int


def _make(table: str, label: str, rows: list[list[object]]) -> LegacySnapshot:
    if table not in SCHEMAS or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", label):
        raise MigrationRejected("EXPLICIT_SUPPORTED_TABLE_AND_LABEL_REQUIRED")
    if not 1 <= len(rows) <= MAX_ROWS:
        raise MigrationRejected("NONEMPTY_WHOLE_TABLE_ROW_BOUND")
    encoded = sorted(rows, key=canonical)
    keys = [canonical([row[i] for i in KEYS[table]]) for row in encoded]
    if any(any(row[i] is None for i in KEYS[table]) for row in encoded):
        raise MigrationRejected("LEGACY_KEY_UNKNOWN")
    if len(set(keys)) != len(keys):
        raise MigrationRejected("DUPLICATE_LEGACY_KEY_NO_WINNER")
    raw = canonical(
        dict(version=VERSION, table=table, source_label=label, columns=SCHEMAS[table], rows=encoded)
    )
    if len(raw) > MAX_BYTES:
        raise MigrationRejected("SNAPSHOT_BYTE_BOUND")
    return LegacySnapshot(digest(raw), raw, len(rows))


def capture_legacy_table(source: Any, *, table: str, source_label: str) -> LegacySnapshot:
    """Owned read-only source, entire explicitly selected table, no outer transaction.

    Maximum 1000 rows: never LIMIT-and-promote a partial table. SQL output bounds
    are not scan-cost or process-memory ceilings. No source file hashing claim.
    """
    if table not in SCHEMAS or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", source_label):
        raise MigrationRejected("EXPLICIT_SUPPORTED_TABLE_AND_LABEL_REQUIRED")
    databases = source.execute(
        "SELECT readonly FROM duckdb_databases() WHERE database_name=current_database()"
    ).fetchall()
    if databases != [(True,)]:
        raise MigrationRejected("READONLY_LEGACY_SOURCE_REQUIRED")
    target = _name(source, "main", table)
    source.execute("BEGIN TRANSACTION")
    try:
        schema = source.execute(
            "SELECT column_name,data_type FROM information_schema.columns "
            "WHERE table_catalog=current_database() AND table_schema='main' AND table_name=? "
            "ORDER BY ordinal_position LIMIT 24",
            [table],
        ).fetchall()
        objects = source.execute(
            "SELECT table_type FROM information_schema.tables WHERE table_catalog="
            "current_database() AND table_schema='main' AND table_name=?",
            [table],
        ).fetchall()
        if tuple(schema) != SCHEMAS[table] or objects != [("BASE TABLE",)]:
            raise MigrationRejected("EXACT_LEGACY_SCHEMA_REQUIRED")
        texts = [n for n, t in SCHEMAS[table] if t in ("VARCHAR", "JSON")]
        checks = " OR ".join(
            f"octet_length(encode(CAST({_quote(n)} AS VARCHAR)))>{MAX_CELL}" for n in texts
        )
        if source.execute(f"SELECT 1 FROM {target} WHERE {checks} LIMIT 1").fetchone():
            raise MigrationRejected("TEXT_CELL_BOUND")
        columns = ",".join(_quote(n) for n, _t in SCHEMAS[table])
        records = source.execute(f"SELECT {columns} FROM {target} LIMIT {MAX_ROWS + 1}").fetchall()
        if not 1 <= len(records) <= MAX_ROWS:
            raise MigrationRejected("NONEMPTY_WHOLE_TABLE_ROW_BOUND")
        rows = [
            [_cell(v, t) for v, (_n, t) in zip(r, SCHEMAS[table], strict=True)] for r in records
        ]
        value = _make(table, source_label, rows)
        source.execute("COMMIT")
        return value
    except BaseException:
        source.execute("ROLLBACK")
        raise


def replay_legacy_snapshot(raw: bytes, *, expected_snapshot_id: str) -> dict[str, Any]:
    """Typed retained-record replay; not original provider-byte or authority replay."""
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_BYTES:
        raise MigrationRejected("SNAPSHOT_BYTE_BOUND")
    if not _pin(expected_snapshot_id) or digest(raw) != expected_snapshot_id:
        raise MigrationRejected("EXACT_SNAPSHOT_PIN_REQUIRED")
    try:
        doc = json.loads(raw)
        table = doc["table"]
        schema = SCHEMAS[table]
        rows = doc["rows"]
        if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_ROWS:
            raise MigrationRejected("NONEMPTY_WHOLE_TABLE_ROW_BOUND")
        checked: list[list[object]] = []
        for row in rows:
            if not isinstance(row, list) or len(row) != len(schema):
                raise MigrationRejected("ROW_SCHEMA_MISMATCH")
            values: list[object] = []
            for value, (_, kind) in zip(row, schema, strict=True):
                original = value
                if value is not None:
                    if type(value) is not str:
                        raise MigrationRejected("EXACT_STORED_CELL_REQUIRED")
                    if kind == "DOUBLE":
                        value = float.fromhex(value)
                    elif kind in ("INTEGER", "BIGINT"):
                        value = int(value)
                        bound = 2**31 if kind == "INTEGER" else 2**63
                        if not -bound <= value < bound:
                            raise MigrationRejected("INTEGER_RANGE")
                    elif kind == "TIMESTAMP WITH TIME ZONE":
                        value = datetime.fromisoformat(value)
                    elif kind == "DATE":
                        value = date.fromisoformat(value)
                if _cell(value, kind) != original:
                    raise MigrationRejected("NONCANONICAL_STORED_CELL")
                values.append(original)
            checked.append(values)
        rebuilt = _make(table, doc["source_label"], checked)
        if doc.get("version") != VERSION or rebuilt.payload != raw:
            raise MigrationRejected("COMPLETE_SNAPSHOT_REPLAY_MISMATCH")
        return doc
    except MigrationRejected:
        raise
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        raise MigrationRejected("MALFORMED_LEGACY_SNAPSHOT") from None


def typed_legacy_observations(
    raw: bytes,
    *,
    expected_snapshot_id: str,
) -> tuple[dict[str, Any], ...]:
    """Source-linked typed projection; legacy analytics are not native recomputation."""
    doc = replay_legacy_snapshot(raw, expected_snapshot_id=expected_snapshot_id)
    result = []
    for ordinal, row in enumerate(doc["rows"]):
        fields = {
            name: value for (name, _kind), value in zip(SCHEMAS[doc["table"]], row, strict=True)
        }
        result.append(
            dict(
                snapshot_id=expected_snapshot_id,
                ordinal=ordinal,
                table=doc["table"],
                stored_fields=fields,
                legacy_derived_fields={k: v for k, v in fields.items() if k in DERIVED},
                source_time_semantics="LEGACY_STORED_TS_NOT_INDEPENDENT_AVAILABILITY",
                original_provider_bytes_retained=False,
                identity_verified=False,
                availability_evidence_verified=False,
                decision_eligibility_asserted=False,
            )
        )
    return tuple(result)


def _paths(conn: Any) -> set[Path]:
    return {Path(r[2]).resolve() for r in conn.execute("PRAGMA database_list").fetchall() if r[2]}


def preserve_legacy_snapshot(
    source: Any,
    bronze: Any,
    *,
    table: str,
    source_label: str,
    expected_snapshot_id: str,
    imported_at: datetime,
    actor_id: str,
    code_revision: str,
) -> dict[str, object]:
    """Existing initialized native target; first write only per label/table/pin.

    imported_at is explicitly the snapshot-import receipt, NEVER original provider
    receipt/availability. No initialization, CLI, repair, retry or hold-release flag.
    Caller owns separate connections and no outer transactions. Synthetic QA only
    until real-data migration hold is explicitly released operationally.
    """
    from nse_quant.data_platform.audit import AuditLedger
    from nse_quant.data_platform.bronze import BronzeEvent, BronzeEventStore

    if not _pin(expected_snapshot_id) or re.fullmatch(r"[a-f0-9]{40}", code_revision) is None:
        raise MigrationRejected("REVIEWED_FULL_PINS_REQUIRED")
    if (
        type(actor_id) is not str
        or not 1 <= len(actor_id) <= 128
        or actor_id != actor_id.strip()
        or any(ord(c) < 32 for c in actor_id)
    ):
        raise MigrationRejected("BOUNDED_ACTOR_REQUIRED")
    _cell(imported_at, "TIMESTAMP WITH TIME ZONE")
    if imported_at is None:
        raise MigrationRejected("IMPORT_RECEIPT_TIME_REQUIRED")
    if not _paths(bronze):
        raise MigrationRejected("FILE_BACKED_NATIVE_TARGET_REQUIRED")
    if source is bronze or any(
        a == b or a.samefile(b) for a in _paths(source) for b in _paths(bronze)
    ):
        raise MigrationRejected("SEPARATE_NATIVE_TARGET_REQUIRED")
    store = BronzeEventStore(bronze)
    store.verify_target()
    scope = digest(canonical([VERSION, table, source_label, expected_snapshot_id]))
    jobs = _name(bronze, "medallion_audit", "jobs")
    if bronze.execute(
        f"SELECT 1 FROM {jobs} WHERE scope_ref=? LIMIT 1", ["sha256:" + scope]
    ).fetchone():
        raise MigrationRejected("ORIGINAL_OBLIGATION_FIRST_WRITE_ONLY")
    ledger = AuditLedger(bronze)
    job = ledger.plan_job(
        command_name=COMMAND,
        actor_id=actor_id,
        scope_ref="sha256:" + scope,
        code_revision=code_revision,
        config_hash=digest(canonical(SCHEMAS)),
    )
    with ledger.execution(job):
        first = capture_legacy_table(source, table=table, source_label=source_label)
        if first.snapshot_id != expected_snapshot_id:
            raise MigrationRejected("REVIEWED_SOURCE_CHANGED")
        second = capture_legacy_table(source, table=table, source_label=source_label)
        if first != second:
            raise MigrationRejected("SOURCE_CHANGED_DURING_CAPTURE")
        replay_legacy_snapshot(first.payload, expected_snapshot_id=expected_snapshot_id)
        event = BronzeEvent(
            "legacy_market_table_snapshot",
            scope,
            table,
            imported_at,
            first.payload,
            VERSION,
            "legacy_snapshot",
        )
        receipt = store.append_batch(
            (event,), batch_key=scope, input_artifact=first.payload, job_id=job
        )
        if receipt.inserted_variants != 1 or receipt.conflict_variants or receipt.exact_retries:
            raise MigrationRejected("UNEXPECTED_NATIVE_BATCH_REUSE")
    return dict(
        snapshot_id=first.snapshot_id,
        row_count=first.row_count,
        job_id=job,
        capture_event_id=event.capture_event_id,
        envelope_hash=event.envelope_hash,
        batch_key=scope,
        decision_eligibility_asserted=False,
    )


def read_preserved_legacy_snapshot(
    bronze: Any,
    *,
    capture_event_id: str,
    envelope_hash: str,
    expected_snapshot_id: str,
) -> tuple[dict[str, Any], ...]:
    """Verify original retained native batch and audit, not current legacy source."""
    from nse_quant.data_platform.bronze import BronzeEvent, BronzeEventStore

    if not all(_pin(x) for x in (capture_event_id, envelope_hash, expected_snapshot_id)):
        raise MigrationRejected("REVIEWED_FULL_PINS_REQUIRED")
    if bronze.execute(
        "SELECT readonly FROM duckdb_databases() WHERE database_name=current_database()"
    ).fetchall() != [(True,)]:
        raise MigrationRejected("READONLY_NATIVE_SOURCE_REQUIRED")
    store = BronzeEventStore(bronze)
    store.verify_target()
    variants = store.object_name("event_variants")
    batches = store.object_name("ingest_batches")
    artifacts = store.object_name("input_artifacts")
    jobs = _name(bronze, "medallion_audit", "jobs")
    events = _name(bronze, "medallion_audit", "job_events")
    bronze.execute("BEGIN TRANSACTION")
    try:
        rows = bronze.execute(
            f"SELECT source,capture_session_id,source_record_id,received_at,"
            f"CASE WHEN octet_length(payload)<=? THEN payload END,payload_hash,"
            f"payload_format,origin_kind,exchange_ts,first_batch_key,first_job_id,"
            f"CASE WHEN length(envelope_json)<=8192 THEN envelope_json END "
            f"FROM {variants} "
            "WHERE capture_event_id=? LIMIT 3",
            [MAX_BYTES, capture_event_id],
        ).fetchall()
        if len(rows) != 1 or rows[0][4] is None:
            raise MigrationRejected("EXACT_SINGLE_NATIVE_VARIANT_REQUIRED")
        row = rows[0]
        raw = bytes(row[4])
        doc = replay_legacy_snapshot(raw, expected_snapshot_id=expected_snapshot_id)
        scope = digest(
            canonical([VERSION, doc["table"], doc["source_label"], expected_snapshot_id])
        )
        rebuilt = BronzeEvent(
            "legacy_market_table_snapshot",
            scope,
            doc["table"],
            row[3],
            raw,
            VERSION,
            "legacy_snapshot",
        )
        if (
            row[:3] != (rebuilt.source, scope, doc["table"])
            or row[5:10] != (expected_snapshot_id, VERSION, "legacy_snapshot", None, scope)
            or row[11] != rebuilt.envelope_json
            or rebuilt.envelope_hash != envelope_hash
            or rebuilt.capture_event_id != capture_event_id
        ):
            raise MigrationRejected("NATIVE_ENVELOPE_BINDING_MISMATCH")
        job = bronze.execute(
            f"SELECT job_id,parent_job_id,command_name,actor_id,scope_ref,code_revision,"
            f"config_hash FROM {jobs} WHERE scope_ref=? LIMIT 3",
            ["sha256:" + scope],
        ).fetchall()
        history = bronze.execute(
            f"SELECT event_index,state,reason_code FROM {events} WHERE job_id=? "
            "ORDER BY event_index LIMIT 5",
            [row[10]],
        ).fetchall()
        batch = bronze.execute(
            f"SELECT batch_fingerprint,input_file_hash,input_events,inserted_variants,"
            f"exact_retries,conflict_variants,job_id FROM {batches} WHERE batch_key=?",
            [scope],
        ).fetchall()
        artifact = bronze.execute(
            f"SELECT CASE WHEN octet_length(artifact_bytes)<=? THEN artifact_bytes END,"
            f"first_job_id FROM {artifacts} WHERE artifact_hash=?",
            [MAX_BYTES, expected_snapshot_id],
        ).fetchall()
        bronze.execute("COMMIT")
    except BaseException:
        bronze.execute("ROLLBACK")
        raise
    if (
        len(job) != 1
        or job[0][0] != row[10]
        or job[0][1] is not None
        or job[0][2] != COMMAND
        or not job[0][3]
        or re.fullmatch(r"[a-f0-9]{40}", job[0][5]) is None
        or job[0][6] != digest(canonical(SCHEMAS))
        or history != [(1, "PLANNED", None), (2, "RUNNING", None), (3, "SUCCEEDED", None)]
    ):
        raise MigrationRejected("ORIGINAL_NATIVE_AUDIT_NOT_VERIFIED")
    fingerprint = digest(
        canonical(
            dict(input_file_hash=expected_snapshot_id, events=[(capture_event_id, envelope_hash)])
        )
    )
    if (
        batch != [(fingerprint, expected_snapshot_id, 1, 1, 0, 0, row[10])]
        or len(artifact) != 1
        or artifact[0][0] is None
        or bytes(artifact[0][0]) != raw
    ):
        raise MigrationRejected("ORIGINAL_NATIVE_BATCH_NOT_VERIFIED")
    return typed_legacy_observations(raw, expected_snapshot_id=expected_snapshot_id)
