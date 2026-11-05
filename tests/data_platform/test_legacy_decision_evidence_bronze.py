"""Actual legacy evidence writer -> native Bronze; no source timezone/admission invention."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import duckdb
import pytest

from nse_quant.data_platform import legacy_daily_rv_bronze as common
from nse_quant.data_platform import legacy_decision_evidence as codec
from nse_quant.data_platform import legacy_decision_evidence_bronze as native
from nse_quant.data_platform.audit import AuditLedger, JobState
from nse_quant.data_platform.bronze import BronzeEventStore
from nse_quant.persistence.duckdb_store import DuckDBStore

WALL = datetime(2026, 1, 1, 9, 15, 0, 123456)
IMPORT_AT = datetime(2026, 1, 2, tzinfo=UTC)
REVISION = "a" * 40
OPAQUE = 'not-json: { "available":true, "eligible":true, "eligible":false }'


def _source(path: Path) -> None:
    legacy = DuckDBStore(path=path)
    try:
        legacy.write_decision_evidence(
            run_id="run",
            ts=WALL,
            symbol="NIFTY",
            plugin="plugin-A",
            evidence={"available": True, "reason": "first", "details": {"value": 1}},
        )
        table = common.name(legacy.conn, "main", codec.TABLE)
        first = legacy.conn.execute(f"SELECT evidence_id FROM {table}").fetchone()
        assert first is not None
        legacy.write_decision_evidence(
            run_id="run",
            ts=WALL,
            symbol="NIFTY",
            plugin="plugin-A",
            evidence={"available": False, "reason": "replacement", "details": {"value": 2}},
        )
        retained = legacy.conn.execute(f"SELECT evidence_id FROM {table}").fetchone()
        assert retained is not None and retained == first
        legacy.write_decision_evidence(
            run_id="run",
            ts=WALL + timedelta(seconds=1),
            symbol="NIFTY",
            plugin="plugin-B",
            evidence={"available": True, "reason": "second"},
        )
        # Deliberate opaque-TEXT boundary; not actual changed-source authorization evidence.
        legacy.conn.execute(
            f"INSERT INTO {table} VALUES (?,?,?,?,?,?,?)",
            ["opaque", "run", WALL + timedelta(seconds=2), "NIFTY", "plugin-C", True, OPAQUE],
        )
    finally:
        legacy.close()


def _record(tmp_path: Path) -> tuple[Path, Path, dict[str, Any]]:
    source_path = tmp_path / "legacy.duckdb"
    bronze_path = tmp_path / "bronze.duckdb"
    _source(source_path)
    source = duckdb.connect(str(source_path), read_only=True)
    target = duckdb.connect(str(bronze_path))
    try:
        AuditLedger(target).initialize()
        BronzeEventStore(target).initialize()
        snapshot = native.capture_decision_evidence(source, source_label="fixture")
        receipt = native.preserve_decision_evidence(
            source,
            target,
            source_label="fixture",
            expected_snapshot_id=snapshot.snapshot_id,
            imported_at=IMPORT_AT,
            actor_id="synthetic",
            code_revision=REVISION,
        )
    finally:
        target.close()
        source.close()
    return source_path, bronze_path, receipt


def _args(receipt: dict[str, Any]) -> dict[str, str]:
    return dict(
        source_label=receipt["source_label"],
        snapshot_id=receipt["snapshot_id"],
        capture_event_id=receipt["capture_event_id"],
        envelope_hash=receipt["envelope_hash"],
        expected_recording_fingerprint=receipt["recording_fingerprint"],
    )


def test_actual_writer_native_chain_and_all_stored_fields(tmp_path: Path) -> None:
    source_path, bronze_path, receipt = _record(tmp_path)
    source = duckdb.connect(str(source_path), read_only=True)
    bronze = duckdb.connect(str(bronze_path), read_only=True)
    try:
        records = native.read_decision_evidence_bronze(bronze, **_args(receipt))
        assert records == native.revalidate_decision_evidence_source(
            source, bronze, **_args(receipt)
        )
        assert len(records) == 3
        table = common.name(source, "main", codec.TABLE)
        columns = ",".join('"' + n + '"' for n, _ in codec.SCHEMA)
        originals = source.execute(f"SELECT {columns} FROM {table}").fetchall()
        by_id = {row[0]: row for row in originals}
        for ordinal, raw in enumerate(records):
            doc = codec.parse(raw, codec.MAX_RECORD)
            fields = doc["stored_fields"]
            row = by_id[fields["evidence_id"]]
            assert fields == {
                n: codec.encode_cell(v, kind)
                for v, (n, kind) in zip(row, codec.SCHEMA, strict=True)
            }
            assert fields["ts"].endswith(f".{row[2].microsecond:06d}")
            assert type(fields["available"]) is bool
            assert doc["source_ordinal"] == ordinal
            assert doc["stored_ts_instant"] is None
            assert doc["source_timezone"] is None
            assert doc["original_availability_at"] is None
            assert doc["payload_interpreted"] is False
            assert doc["native_decision_replayed"] is False
            assert doc["decision_eligibility_asserted"] is False
        by_id_docs = {
            codec.parse(r, codec.MAX_RECORD)["stored_fields"]["evidence_id"]: codec.parse(
                r, codec.MAX_RECORD
            )
            for r in records
        }
        opaque = by_id_docs["opaque"]
        assert opaque["stored_fields"]["payload_json"] == OPAQUE
        assert opaque["stored_fields"]["available"] is True
        assert opaque["decision_eligibility_asserted"] is False
    finally:
        bronze.close()
        source.close()


def test_wall_fields_never_infer_a_timezone() -> None:
    assert codec.wall_fields(WALL) == "2026-01-01T09:15:00.123456"
    aware = datetime(2026, 1, 1, 9, 15, 0, 123456, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    with pytest.raises(codec.Rejected, match="NAIVE_STORED_WALL_FIELDS_REQUIRED"):
        codec.wall_fields(aware)
    row = ["E", "R", codec.wall_fields(WALL), "S", "P", True, OPAQUE]
    for value in (aware.isoformat(), "2026-01-01 09:15:00.123456", "2026-01-01T09:15:00"):
        with pytest.raises(codec.Rejected):
            codec.make_snapshot("fixture", [[*row[:2], value, *row[3:]]])
    for malformed_value in (1, 0, "true", "false", None):
        with pytest.raises(codec.Rejected):
            codec.make_snapshot("fixture", [[*row[:5], malformed_value, row[6]]])


def test_both_key_axes_are_reconciled() -> None:
    row = ["E", "R", codec.wall_fields(WALL), "S", "P", False, "raw"]
    with pytest.raises(codec.Rejected, match="DUPLICATE_PRIMARY_OR_NATURAL_EVIDENCE_KEY"):
        codec.make_snapshot("fixture", [row, ["other-id", *row[1:]]])
    with pytest.raises(codec.Rejected, match="DUPLICATE_PRIMARY_OR_NATURAL_EVIDENCE_KEY"):
        codec.make_snapshot("fixture", [row, [row[0], "other-run", *row[2:]]])


def test_current_source_separate_from_original_native_replay(tmp_path: Path) -> None:
    source_path, bronze_path, receipt = _record(tmp_path)
    writer = duckdb.connect(str(source_path))
    try:
        table = common.name(writer, "main", codec.TABLE)
        writer.execute(f"UPDATE {table} SET available=NOT available")
    finally:
        writer.close()
    source = duckdb.connect(str(source_path), read_only=True)
    bronze = duckdb.connect(str(bronze_path), read_only=True)
    try:
        assert len(native.read_decision_evidence_bronze(bronze, **_args(receipt))) == 3
        with pytest.raises(codec.Rejected, match="CURRENT_LEGACY_EVIDENCE_SOURCE_CHANGED"):
            native.revalidate_decision_evidence_source(source, bronze, **_args(receipt))
    finally:
        bronze.close()
        source.close()


def test_wrong_review_cannot_heal(tmp_path: Path) -> None:
    path = tmp_path / "legacy.duckdb"
    _source(path)
    source = duckdb.connect(str(path), read_only=True)
    target = duckdb.connect(str(tmp_path / "bronze.duckdb"))
    try:
        AuditLedger(target).initialize()
        BronzeEventStore(target).initialize()
        with pytest.raises(codec.Rejected, match="REVIEWED_SOURCE_CHANGED"):
            native.preserve_decision_evidence(
                source,
                target,
                source_label="fixture",
                expected_snapshot_id="b" * 64,
                imported_at=IMPORT_AT,
                actor_id="synthetic",
                code_revision=REVISION,
            )
        snapshot = native.capture_decision_evidence(source, source_label="fixture")
        with pytest.raises(codec.Rejected, match="FIRST_WRITE_ORIGINAL_OBLIGATION"):
            native.preserve_decision_evidence(
                source,
                target,
                source_label="fixture",
                expected_snapshot_id=snapshot.snapshot_id,
                imported_at=IMPORT_AT,
                actor_id="other",
                code_revision="c" * 40,
            )
    finally:
        target.close()
        source.close()


@pytest.mark.parametrize(
    "kind",
    ["id", "payload", "artifact", "audit", "clock"],
    ids=["event-id", "payload", "artifact", "audit", "clock"],
)
def test_original_recording_tampering(tmp_path: Path, kind: str) -> None:
    _source_path, path, receipt = _record(tmp_path)
    writer = duckdb.connect(str(path))
    try:
        variants = common.name(writer, "bronze", "event_variants")
        if kind == "id":
            writer.execute(f"UPDATE {variants} SET capture_event_id=?", ["f" * 64])
        elif kind == "payload":
            writer.execute(f"UPDATE {variants} SET payload=?", [b"{}"])
        elif kind == "artifact":
            table = common.name(writer, "bronze", "input_artifacts")
            writer.execute(f"UPDATE {table} SET artifact_bytes=?", [b"{}"])
        elif kind == "audit":
            events = common.name(writer, "medallion_audit", "job_events")
            writer.execute(f"DELETE FROM {events} WHERE state='SUCCEEDED'")
        else:
            writer.execute(f"UPDATE {variants} SET recorded_at=recorded_at+INTERVAL '1 second'")
    finally:
        writer.close()
    reader = duckdb.connect(str(path), read_only=True)
    try:
        with pytest.raises(codec.Rejected):
            native.read_decision_evidence_bronze(reader, **_args(receipt))
    finally:
        reader.close()


@pytest.mark.parametrize(
    "kind",
    ["view", "aware-schema", "null", "duplicate-primary", "duplicate-natural", "empty", "overflow"],
    ids=["view", "aware-schema", "null", "primary", "natural", "empty", "rows"],
)
def test_schema_key_and_whole_table_boundaries(tmp_path: Path, kind: str) -> None:
    path = tmp_path / "legacy.duckdb"
    writer = duckdb.connect(str(path))
    try:
        table = common.name(writer, "main", codec.TABLE)
        if kind == "view":
            writer.execute(f"CREATE VIEW {table} AS SELECT 1 AS wrong")
        else:
            columns = ",".join(
                f'"{n}" {"TIMESTAMPTZ" if n == "ts" and kind == "aware-schema" else k}'
                for n, k in codec.SCHEMA
            )
            writer.execute(f"CREATE TABLE {table} ({columns})")
            if kind != "empty":
                writer.execute(
                    f"INSERT INTO {table} VALUES (?,?,?,?,?,?,?)",
                    ["E", "R", WALL, "S", "P", None if kind == "null" else True, "raw"],
                )
            if kind == "duplicate-primary":
                writer.execute(
                    f"INSERT INTO {table} SELECT evidence_id,'other',ts,symbol,plugin,"
                    f"available,payload_json FROM {table}"
                )
            elif kind == "duplicate-natural":
                writer.execute(
                    f"INSERT INTO {table} SELECT 'other',run_id,ts,symbol,plugin,"
                    f"available,payload_json FROM {table}"
                )
            elif kind == "overflow":
                writer.execute(
                    f"INSERT INTO {table} SELECT t.* FROM {table} t CROSS JOIN range(1000)"
                )
    finally:
        writer.close()
    reader = duckdb.connect(str(path), read_only=True)
    try:
        with pytest.raises(codec.Rejected):
            native.capture_decision_evidence(reader, source_label="fixture")
        assert reader.execute("SELECT 1").fetchone() == (1,)
    finally:
        reader.close()


@pytest.mark.parametrize("text", ["x" * 65536, "x" * 65537], ids=["text-limit", "text-overflow"])
def test_payload_text_bounds(tmp_path: Path, text: str) -> None:
    path = tmp_path / "legacy.duckdb"
    _source(path)
    writer = duckdb.connect(str(path))
    try:
        table = common.name(writer, "main", codec.TABLE)
        writer.execute(f"UPDATE {table} SET payload_json=?", [text])
    finally:
        writer.close()
    reader = duckdb.connect(str(path), read_only=True)
    try:
        if len(text) > codec.MAX_CELL:
            with pytest.raises(codec.Rejected, match="TEXT_TRANSFER_BOUND"):
                native.capture_decision_evidence(reader, source_label="fixture")
        else:
            assert native.capture_decision_evidence(reader, source_label="fixture").row_count == 3
    finally:
        reader.close()


def test_sql_partial_batch_rollback(tmp_path: Path) -> None:
    path = tmp_path / "legacy.duckdb"
    _source(path)
    source = duckdb.connect(str(path), read_only=True)
    owner = duckdb.connect(str(tmp_path / "bronze.duckdb"))

    class Fail:
        def execute(self, sql: str, parameters: Any = None) -> Any:
            if sql.lstrip().startswith("INSERT INTO") and '"event_variants"' in sql:
                raise RuntimeError("INJECTED_VARIANT_SQL_FAILURE")
            return owner.execute(sql) if parameters is None else owner.execute(sql, parameters)

    try:
        AuditLedger(owner).initialize()
        BronzeEventStore(owner).initialize()
        snapshot = native.capture_decision_evidence(source, source_label="fixture")
        with pytest.raises(RuntimeError, match="INJECTED_VARIANT_SQL_FAILURE"):
            native.preserve_decision_evidence(
                source,
                Fail(),
                source_label="fixture",
                expected_snapshot_id=snapshot.snapshot_id,
                imported_at=IMPORT_AT,
                actor_id="synthetic",
                code_revision=REVISION,
            )
        for table in ("event_variants", "input_artifacts", "ingest_batches"):
            qualified = common.name(owner, "bronze", table)
            assert owner.execute(f"SELECT count(*) FROM {qualified}").fetchone() == (0,)
        with pytest.raises(codec.Rejected, match="FIRST_WRITE_ORIGINAL_OBLIGATION"):
            native.preserve_decision_evidence(
                source,
                owner,
                source_label="fixture",
                expected_snapshot_id=snapshot.snapshot_id,
                imported_at=IMPORT_AT,
                actor_id="synthetic",
                code_revision=REVISION,
            )
    finally:
        owner.close()
        source.close()


def test_final_audit_failure_blocks_read(tmp_path: Path, monkeypatch: Any) -> None:
    path = tmp_path / "legacy.duckdb"
    _source(path)
    source = duckdb.connect(str(path), read_only=True)
    bronze_path = tmp_path / "bronze.duckdb"
    target = duckdb.connect(str(bronze_path))
    actual = AuditLedger.transition

    def fail(self: Any, job: str, state: JobState, reason_code: str | None = None) -> None:
        if state == JobState.SUCCEEDED:
            raise RuntimeError("INJECTED_FINAL_AUDIT_FAILURE")
        actual(self, job, state, reason_code)

    try:
        AuditLedger(target).initialize()
        BronzeEventStore(target).initialize()
        snapshot = native.capture_decision_evidence(source, source_label="fixture")
        monkeypatch.setattr(AuditLedger, "transition", fail)
        with pytest.raises(RuntimeError, match="INJECTED_FINAL_AUDIT_FAILURE"):
            native.preserve_decision_evidence(
                source,
                target,
                source_label="fixture",
                expected_snapshot_id=snapshot.snapshot_id,
                imported_at=IMPORT_AT,
                actor_id="synthetic",
                code_revision=REVISION,
            )
        table = common.name(target, "bronze", "event_variants")
        row = target.execute(f"SELECT capture_event_id,envelope_hash FROM {table}").fetchone()
        assert row is not None
    finally:
        target.close()
        source.close()
    reader = duckdb.connect(str(bronze_path), read_only=True)
    try:
        with pytest.raises(codec.Rejected, match="ORIGINAL_EVIDENCE_AUDIT_NOT_VERIFIED"):
            native.read_decision_evidence_bronze(
                reader,
                source_label="fixture",
                snapshot_id=snapshot.snapshot_id,
                capture_event_id=row[0],
                envelope_hash=row[1],
                expected_recording_fingerprint="b" * 64,
            )
    finally:
        reader.close()


def test_alias_and_orphan_rules(tmp_path: Path) -> None:
    source_path, bronze_path, receipt = _record(tmp_path)
    writer = duckdb.connect(str(bronze_path))
    alias = writer.cursor()
    try:
        with pytest.raises(codec.Rejected, match="SEPARATE_TARGET_REQUIRED"):
            native.preserve_decision_evidence(
                alias,
                writer,
                source_label="fixture",
                expected_snapshot_id=receipt["snapshot_id"],
                imported_at=IMPORT_AT,
                actor_id="synthetic",
                code_revision=REVISION,
            )
        assert writer.execute("SELECT 1").fetchone() == (1,)
        for table in ("job_events", "jobs"):
            writer.execute(f"DELETE FROM {common.name(writer, 'medallion_audit', table)}")
    finally:
        alias.close()
        writer.close()
    source = duckdb.connect(str(source_path), read_only=True)
    target = duckdb.connect(str(bronze_path))
    try:
        with pytest.raises(codec.Rejected, match="FIRST_WRITE_ORIGINAL_OBLIGATION"):
            native.preserve_decision_evidence(
                source,
                target,
                source_label="fixture",
                expected_snapshot_id=receipt["snapshot_id"],
                imported_at=IMPORT_AT,
                actor_id="synthetic",
                code_revision=REVISION,
            )
    finally:
        target.close()
        source.close()


def test_session_timezone_does_not_reinterpret_source_wall_fields(tmp_path: Path) -> None:
    path = tmp_path / "legacy.duckdb"
    _source(path)
    source = duckdb.connect(str(path), read_only=True)
    try:
        source.execute("SET TimeZone='UTC'")
        first = native.capture_decision_evidence(source, source_label="fixture")
        source.execute("SET TimeZone='Asia/Kolkata'")
        second = native.capture_decision_evidence(source, source_label="fixture")
        assert first == second
    finally:
        source.close()


def test_second_actual_capture_then_injected_drift(tmp_path: Path, monkeypatch: Any) -> None:
    path = tmp_path / "legacy.duckdb"
    _source(path)
    source = duckdb.connect(str(path), read_only=True)
    target = duckdb.connect(str(tmp_path / "bronze.duckdb"))
    actual = native.capture_decision_evidence
    count = 0

    def drift(conn: Any, *, source_label: str) -> codec.Snapshot:
        nonlocal count
        value = actual(conn, source_label=source_label)
        count += 1
        if count == 2:
            # Negative boundary after a real capture, not authentic source drift.
            doc = codec.parse(value.payload, codec.MAX_BYTES)
            doc["rows"][0][5] = not doc["rows"][0][5]
            return codec.make_snapshot(source_label, doc["rows"])
        return value

    try:
        AuditLedger(target).initialize()
        BronzeEventStore(target).initialize()
        snapshot = actual(source, source_label="fixture")
        monkeypatch.setattr(native, "capture_decision_evidence", drift)
        with pytest.raises(codec.Rejected, match="SOURCE_CHANGED_DURING_CAPTURE"):
            native.preserve_decision_evidence(
                source,
                target,
                source_label="fixture",
                expected_snapshot_id=snapshot.snapshot_id,
                imported_at=IMPORT_AT,
                actor_id="synthetic",
                code_revision=REVISION,
            )
    finally:
        target.close()
        source.close()


def test_projection_bound_rejects_before_native_append(tmp_path: Path) -> None:
    path = tmp_path / "legacy.duckdb"
    _source(path)
    writer = duckdb.connect(str(path))
    try:
        table = common.name(writer, "main", codec.TABLE)
        writer.execute(f"DELETE FROM {table}")
        writer.execute(
            f"INSERT INTO {table} VALUES (?,?,?,?,?,?,?)",
            ["e" * 65536, "r" * 65536, WALL, "s" * 65536, "p" * 65536, True, "\x01" * 65536],
        )
    finally:
        writer.close()
    source = duckdb.connect(str(path), read_only=True)
    target = duckdb.connect(str(tmp_path / "bronze.duckdb"))
    try:
        AuditLedger(target).initialize()
        BronzeEventStore(target).initialize()
        snapshot = native.capture_decision_evidence(source, source_label="fixture")
        assert len(snapshot.payload) <= codec.MAX_BYTES
        with pytest.raises(codec.Rejected, match="EVIDENCE_RECORD_BYTE_BOUND"):
            native.preserve_decision_evidence(
                source,
                target,
                source_label="fixture",
                expected_snapshot_id=snapshot.snapshot_id,
                imported_at=IMPORT_AT,
                actor_id="synthetic",
                code_revision=REVISION,
            )
        for table in ("event_variants", "input_artifacts", "ingest_batches"):
            qualified = common.name(target, "bronze", table)
            assert target.execute(f"SELECT count(*) FROM {qualified}").fetchone() == (0,)
    finally:
        target.close()
        source.close()


def test_outer_contract_is_strict_but_payload_is_not_parsed() -> None:
    row = ["E", "R", codec.wall_fields(WALL), "S", "P", True, OPAQUE]
    snapshot = codec.make_snapshot("fixture", [row])
    doc = codec.parse(snapshot.payload, codec.MAX_BYTES)
    doc["unknown"] = True
    changed = codec.canonical(doc)
    with pytest.raises(codec.Rejected, match="COMPLETE_DECISION_EVIDENCE_REPLAY_MISMATCH"):
        codec.replay_snapshot(changed, expected_snapshot_id=codec.sha(changed))
    duplicate = b'{"version":1,"version":2}'
    with pytest.raises(codec.Rejected, match="DUPLICATE_JSON_KEY"):
        codec.replay_snapshot(duplicate, expected_snapshot_id=codec.sha(duplicate))
