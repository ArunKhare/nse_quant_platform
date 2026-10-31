"""Append-only payload storage using fully qualified catalog/schema/object names."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock

import duckdb


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _instant(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Use timezone-aware observation timestamps")
    return value.astimezone(UTC).isoformat()


def qualified_bronze_name(conn: duckdb.DuckDBPyConnection, name: str) -> str:
    """Quote a table/sequence name in the connection's current catalog and Bronze schema."""
    row = conn.execute("SELECT current_database()").fetchone()
    if row is None:
        raise RuntimeError("Current database is unavailable")
    parts = (str(row[0]), "bronze", name)
    return ".".join('"' + part.replace('"', '""') + '"' for part in parts)


@dataclass(frozen=True)
class BronzeEvent:
    source: str
    capture_session_id: str
    source_record_id: str
    received_at: datetime
    payload: bytes
    payload_format: str
    origin_kind: str
    exchange_ts: datetime | None = None
    provider_event_id: str | None = None
    instrument_ref: str | None = None

    def __post_init__(self) -> None:
        if any(
            not value.strip()
            for value in (
                self.source,
                self.capture_session_id,
                self.source_record_id,
                self.payload_format,
            )
        ):
            raise ValueError("Source/session/record/format identities are required")
        if self.origin_kind not in {"live_provider", "historical_import", "legacy_snapshot"}:
            raise ValueError("Explicit origin kind is required")
        if not isinstance(self.payload, bytes):
            raise TypeError("Payload must be exact bytes, not a mutable decoded object")
        _instant(self.received_at)
        if self.exchange_ts is not None:
            _instant(self.exchange_ts)

    @property
    def capture_event_id(self) -> str:
        return sha256(
            _json(
                [
                    self.source,
                    self.capture_session_id,
                    self.source_record_id,
                ]
            ).encode()
        )

    @property
    def payload_hash(self) -> str:
        return sha256(self.payload)

    @property
    def envelope_json(self) -> str:
        return _json(
            {
                "envelope_version": 1,
                "source": self.source,
                "capture_session_id": self.capture_session_id,
                "source_record_id": self.source_record_id,
                "received_at": _instant(self.received_at),
                "payload_hash": self.payload_hash,
                "payload_format": self.payload_format,
                "origin_kind": self.origin_kind,
                "exchange_ts": _instant(self.exchange_ts) if self.exchange_ts else None,
                "provider_event_id": self.provider_event_id,
                "instrument_ref": self.instrument_ref,
            }
        )

    @property
    def envelope_hash(self) -> str:
        return sha256(self.envelope_json.encode())


@dataclass(frozen=True)
class BronzeReceipt:
    batch_key: str
    batch_fingerprint: str
    inserted_variants: int
    exact_retries: int
    conflict_variants: int
    last_sequence: int | None
    already_committed: bool = False


class BronzeEventStore:
    def __init__(self, conn: duckdb.DuckDBPyConnection) -> None:
        self.conn = conn
        self._lock = Lock()

    def object_name(self, name: str) -> str:
        return qualified_bronze_name(self.conn, name)

    def verify_target(self, *, require_initialized: bool = True) -> None:
        forbidden = self.conn.execute(
            """SELECT table_name FROM information_schema.tables
            WHERE table_catalog = current_database()
              AND table_schema NOT IN ('bronze', 'medallion_audit')"""
        ).fetchall()
        if forbidden:
            raise ValueError("Use a dedicated Bronze DB, not the legacy source database")
        if require_initialized:
            versions = self.conn.execute(
                f"SELECT version FROM {self.object_name('schema_versions')}"
            ).fetchall()
            if versions != [(1,)]:
                raise ValueError("Unsupported Bronze schema version")

    def initialize(self) -> None:
        """Explicit initialization; never rename a catalog/schema to resolve ambiguity."""
        with self._lock:
            self.verify_target(require_initialized=False)
            names = {
                name: self.object_name(name)
                for name in (
                    "schema_versions",
                    "ingest_sequence",
                    "event_variants",
                    "input_artifacts",
                    "ingest_batches",
                )
            }
            schema = self.object_name("placeholder").rsplit(".", 1)[0]
            sequence_literal = names["ingest_sequence"].replace("'", "''")
            self.conn.execute("BEGIN TRANSACTION")
            try:
                self.conn.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
                self.conn.execute(
                    f"CREATE TABLE IF NOT EXISTS {names['schema_versions']} "
                    "(version INTEGER PRIMARY KEY)"
                )
                versions = self.conn.execute(
                    f"SELECT version FROM {names['schema_versions']}"
                ).fetchall()
                if versions and versions != [(1,)]:
                    raise ValueError("Unsupported Bronze schema version")
                self.conn.execute(
                    f"CREATE SEQUENCE IF NOT EXISTS {names['ingest_sequence']} START 1"
                )
                self.conn.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {names["event_variants"]} (
                        capture_event_id VARCHAR NOT NULL,
                        envelope_hash VARCHAR NOT NULL,
                        ingest_sequence BIGINT DEFAULT nextval('{sequence_literal}'),
                        source VARCHAR NOT NULL,
                        capture_session_id VARCHAR NOT NULL,
                        source_record_id VARCHAR NOT NULL,
                        received_at TIMESTAMPTZ NOT NULL,
                        recorded_at TIMESTAMPTZ NOT NULL,
                        exchange_ts TIMESTAMPTZ,
                        payload BLOB NOT NULL,
                        payload_hash VARCHAR NOT NULL,
                        payload_format VARCHAR NOT NULL,
                        origin_kind VARCHAR NOT NULL,
                        envelope_json VARCHAR NOT NULL,
                        first_batch_key VARCHAR NOT NULL,
                        first_job_id VARCHAR NOT NULL,
                        PRIMARY KEY (capture_event_id, envelope_hash)
                    )
                    """
                )
                self.conn.execute(
                    f"""CREATE TABLE IF NOT EXISTS {names["input_artifacts"]} (
                        artifact_hash VARCHAR PRIMARY KEY,
                        artifact_bytes BLOB NOT NULL,
                        recorded_at TIMESTAMPTZ NOT NULL,
                        first_job_id VARCHAR NOT NULL
                    )"""
                )
                self.conn.execute(
                    f"""CREATE TABLE IF NOT EXISTS {names["ingest_batches"]} (
                        batch_key VARCHAR PRIMARY KEY,
                        batch_fingerprint VARCHAR NOT NULL,
                        input_file_hash VARCHAR NOT NULL,
                        input_events BIGINT NOT NULL,
                        inserted_variants BIGINT NOT NULL,
                        exact_retries BIGINT NOT NULL,
                        conflict_variants BIGINT NOT NULL,
                        last_sequence BIGINT,
                        job_id VARCHAR NOT NULL,
                        committed_at TIMESTAMPTZ NOT NULL
                    )"""
                )
                if not versions:
                    self.conn.execute(f"INSERT INTO {names['schema_versions']} VALUES (1)")
                self.conn.execute("COMMIT")
            except BaseException:
                self.conn.execute("ROLLBACK")
                raise

    def append_batch(
        self,
        events: tuple[BronzeEvent, ...],
        *,
        batch_key: str,
        input_artifact: bytes,
        job_id: str,
        max_events: int = 10_000,
        max_payload_bytes: int = 1_048_576,
    ) -> BronzeReceipt:
        if not isinstance(events, tuple) or not events or len(events) > max_events:
            raise ValueError("Use a nonempty bounded immutable event batch")
        if not batch_key.strip() or not job_id.strip():
            raise ValueError("Batch and audit job identity are required")
        if not isinstance(input_artifact, bytes) or len(input_artifact) > 16_777_216:
            raise ValueError("Use an exact input artifact of at most 16 MiB")
        input_file_hash = sha256(input_artifact)
        if any(len(event.payload) > max_payload_bytes for event in events):
            raise ValueError("Payload exceeds configured capture limit")
        fingerprint = sha256(
            _json(
                {
                    "input_file_hash": input_file_hash,
                    "events": [(event.capture_event_id, event.envelope_hash) for event in events],
                }
            ).encode()
        )
        with self._lock:
            variants_table = self.object_name("event_variants")
            batches_table = self.object_name("ingest_batches")
            artifacts_table = self.object_name("input_artifacts")
            sequence_literal = self.object_name("ingest_sequence").replace("'", "''")
            self.conn.execute("BEGIN TRANSACTION")
            try:
                previous = self.conn.execute(
                    f"SELECT batch_fingerprint, last_sequence FROM {batches_table} "
                    "WHERE batch_key = ?",
                    [batch_key],
                ).fetchone()
                if previous is not None:
                    if previous[0] != fingerprint:
                        raise ValueError("Batch identity reused with different content")
                    self.conn.execute("COMMIT")
                    return BronzeReceipt(
                        batch_key,
                        fingerprint,
                        0,
                        len(events),
                        0,
                        previous[1],
                        already_committed=True,
                    )
                artifact = self.conn.execute(
                    f"SELECT artifact_bytes FROM {artifacts_table} WHERE artifact_hash = ?",
                    [input_file_hash],
                ).fetchone()
                if artifact is None:
                    self.conn.execute(
                        f"INSERT INTO {artifacts_table} VALUES (?, ?, ?, ?)",
                        [input_file_hash, input_artifact, datetime.now(UTC), job_id],
                    )
                elif bytes(artifact[0]) != input_artifact:
                    raise ValueError("Stored input artifact does not match its hash")
                inserted = retries = conflicts = 0
                for event in events:
                    variants = self.conn.execute(
                        f"SELECT envelope_hash FROM {variants_table} WHERE capture_event_id = ?",
                        [event.capture_event_id],
                    ).fetchall()
                    if any(row[0] == event.envelope_hash for row in variants):
                        retries += 1
                        continue
                    conflicts += int(bool(variants))
                    self.conn.execute(
                        f"""INSERT INTO {variants_table} (
                            capture_event_id, envelope_hash, source, capture_session_id,
                            source_record_id, received_at, recorded_at, exchange_ts,
                            payload, payload_hash, payload_format, origin_kind,
                            envelope_json, first_batch_key, first_job_id, ingest_sequence
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                                  nextval('{sequence_literal}'))""",
                        [
                            event.capture_event_id,
                            event.envelope_hash,
                            event.source,
                            event.capture_session_id,
                            event.source_record_id,
                            event.received_at,
                            datetime.now(UTC),
                            event.exchange_ts,
                            event.payload,
                            event.payload_hash,
                            event.payload_format,
                            event.origin_kind,
                            event.envelope_json,
                            batch_key,
                            job_id,
                        ],
                    )
                    inserted += 1
                sequence = self.conn.execute(
                    f"SELECT max(ingest_sequence) FROM {variants_table}"
                ).fetchone()
                last = sequence[0] if sequence is not None else None
                self.conn.execute(
                    f"INSERT INTO {batches_table} VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        batch_key,
                        fingerprint,
                        input_file_hash,
                        len(events),
                        inserted,
                        retries,
                        conflicts,
                        last,
                        job_id,
                        datetime.now(UTC),
                    ],
                )
                self.conn.execute("COMMIT")
                return BronzeReceipt(batch_key, fingerprint, inserted, retries, conflicts, last)
            except BaseException:
                self.conn.execute("ROLLBACK")
                raise

    def conflicting_event_ids(self) -> tuple[str, ...]:
        return tuple(
            row[0]
            for row in self.conn.execute(
                f"SELECT capture_event_id FROM {self.object_name('event_variants')} "
                "GROUP BY capture_event_id HAVING count(*) > 1 ORDER BY capture_event_id"
            ).fetchall()
        )
