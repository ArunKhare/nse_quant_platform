"""Actual synthetic SQL -> native Bronze/audit -> verified projection integration."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import duckdb
import pytest

from nse_quant.data_platform import legacy_daily_rv as codec
from nse_quant.data_platform import legacy_daily_rv_bronze as native
from nse_quant.data_platform.audit import AuditLedger, JobState
from nse_quant.data_platform.bronze import BronzeEventStore

AT = datetime(2026, 1, 1, tzinfo=UTC)
REVISION = "a" * 40


def _source(path: Path, *, rows: int = 2) -> None:
    conn = duckdb.connect(str(path))
    try:
        table = native.name(conn, "main", codec.TABLE)
        conn.execute(
            f"CREATE TABLE {table} (symbol VARCHAR NOT NULL, trading_date DATE NOT NULL,"
            "rv DOUBLE NOT NULL,observation_count BIGINT NOT NULL,"
            "PRIMARY KEY(symbol,trading_date))"
        )
        for i in range(rows):
            conn.execute(
                f"INSERT INTO {table} VALUES (?,DATE '2026-01-01',?,?)",
                [f"S{i}", -0.0 if i == 0 else 0.25, 0 if i == 0 else 10],
            )
    finally:
        conn.close()


def _target(path: Path) -> Any:
    conn = duckdb.connect(str(path))
    AuditLedger(conn).initialize()
    BronzeEventStore(conn).initialize()
    return conn


def _record(tmp_path: Path) -> tuple[Path, Path, dict[str, Any]]:
    legacy = tmp_path / "legacy.duckdb"
    target = tmp_path / "bronze.duckdb"
    _source(legacy)
    source = duckdb.connect(str(legacy), read_only=True)
    bronze = _target(target)
    try:
        snapshot = native.capture_daily_rv(source, source_label="fixture")
        receipt = native.preserve_daily_rv(
            source,
            bronze,
            source_label="fixture",
            expected_snapshot_id=snapshot.snapshot_id,
            imported_at=AT,
            actor_id="synthetic",
            code_revision=REVISION,
        )
    finally:
        bronze.close()
        source.close()
    return legacy, target, receipt


def _pins(receipt: dict[str, Any]) -> dict[str, Any]:
    return dict(
        source_label=receipt["source_label"],
        snapshot_id=receipt["snapshot_id"],
        capture_event_id=receipt["capture_event_id"],
        envelope_hash=receipt["envelope_hash"],
        expected_recording_fingerprint=receipt["recording_fingerprint"],
    )


def test_actual_producer_reader_and_current_sql(tmp_path: Path) -> None:
    legacy, target, receipt = _record(tmp_path)
    source = duckdb.connect(str(legacy), read_only=True)
    bronze = duckdb.connect(str(target), read_only=True)
    try:
        records = native.read_daily_rv_bronze(bronze, **_pins(receipt))
        assert len(records) == 2
        first = json.loads(records[0])
        assert first["stored_fields"]["rv"] == (-0.0).hex()
        assert first["flags"] == ["ZERO_LEGACY_RV", "NONPOSITIVE_OBSERVATION_COUNT"]
        assert first["native_rv_recomputed"] is False
        assert first["decision_eligibility_asserted"] is False
        assert first["original_availability_at"] is None
        assert native.revalidate_daily_rv_source(source, bronze, **_pins(receipt)) == records
    finally:
        bronze.close()
        source.close()


def test_retained_replay_distinct_from_current_sql(tmp_path: Path) -> None:
    legacy, target, receipt = _record(tmp_path)
    writer = duckdb.connect(str(legacy))
    try:
        writer.execute(f"UPDATE {native.name(writer, 'main', codec.TABLE)} SET rv=0.9")
    finally:
        writer.close()
    source = duckdb.connect(str(legacy), read_only=True)
    bronze = duckdb.connect(str(target), read_only=True)
    try:
        assert len(native.read_daily_rv_bronze(bronze, **_pins(receipt))) == 2
        with pytest.raises(codec.Rejected, match="CURRENT_LEGACY_SOURCE_CHANGED"):
            native.revalidate_daily_rv_source(source, bronze, **_pins(receipt))
    finally:
        bronze.close()
        source.close()


def test_failed_review_cannot_heal_with_new_pin(tmp_path: Path) -> None:
    path = tmp_path / "source.duckdb"
    _source(path)
    source = duckdb.connect(str(path), read_only=True)
    bronze = _target(tmp_path / "bronze.duckdb")
    try:
        args = dict(
            source_label="fixture", imported_at=AT, actor_id="synthetic", code_revision=REVISION
        )
        with pytest.raises(codec.Rejected, match="REVIEWED_SOURCE_CHANGED"):
            native.preserve_daily_rv(source, bronze, expected_snapshot_id="b" * 64, **args)
        snapshot = native.capture_daily_rv(source, source_label="fixture")
        with pytest.raises(codec.Rejected, match="FIRST_WRITE_ORIGINAL_OBLIGATION"):
            native.preserve_daily_rv(
                source, bronze, expected_snapshot_id=snapshot.snapshot_id, **args
            )
        events = native.name(bronze, "medallion_audit", "job_events")
        assert bronze.execute(f"SELECT state FROM {events} ORDER BY event_index").fetchall() == [
            ("PLANNED",),
            ("RUNNING",),
            ("FAILED",),
        ]
    finally:
        bronze.close()
        source.close()


@pytest.mark.parametrize(
    "mutation",
    ["payload", "artifact", "audit", "clock", "duplicate_job"],
    ids=["payload", "artifact", "failed-audit", "clock-pin", "duplicate-job"],
)
def test_original_recording_tampering(tmp_path: Path, mutation: str) -> None:
    _legacy, path, receipt = _record(tmp_path)
    writer = duckdb.connect(str(path))
    try:
        if mutation == "payload":
            writer.execute(
                f"UPDATE {native.name(writer, 'bronze', 'event_variants')} SET payload=?", [b"{}"]
            )
        elif mutation == "artifact":
            writer.execute(
                f"UPDATE {native.name(writer, 'bronze', 'input_artifacts')} SET artifact_bytes=?",
                [b"{}"],
            )
        elif mutation == "audit":
            writer.execute(
                f"DELETE FROM {native.name(writer, 'medallion_audit', 'job_events')} "
                "WHERE state='SUCCEEDED'"
            )
        elif mutation == "clock":
            writer.execute(
                f"UPDATE {native.name(writer, 'bronze', 'event_variants')} "
                "SET recorded_at=recorded_at+INTERVAL '1 second'"
            )
        else:
            AuditLedger(writer).plan_job(
                command_name=native.COMMAND,
                actor_id="other",
                scope_ref="sha256:" + native.scope_id("fixture"),
                code_revision=REVISION,
                config_hash="c" * 64,
            )
    finally:
        writer.close()
    reader = duckdb.connect(str(path), read_only=True)
    try:
        with pytest.raises(codec.Rejected):
            native.read_daily_rv_bronze(reader, **_pins(receipt))
    finally:
        reader.close()


def test_second_real_capture_drift(tmp_path: Path, monkeypatch: Any) -> None:
    path = tmp_path / "legacy.duckdb"
    _source(path)
    source = duckdb.connect(str(path), read_only=True)
    bronze = _target(tmp_path / "bronze.duckdb")
    actual = native.capture_daily_rv
    calls = 0

    def drift(conn: Any, *, source_label: str) -> codec.Snapshot:
        nonlocal calls
        value = actual(conn, source_label=source_label)
        calls += 1
        if calls == 2:
            # Deliberate negative-boundary substitution, not authentic source drift.
            return codec.make_snapshot(source_label, [["changed", "2026-01-01", (0.5).hex(), "2"]])
        return value

    try:
        pin = actual(source, source_label="fixture").snapshot_id
        monkeypatch.setattr(native, "capture_daily_rv", drift)
        with pytest.raises(codec.Rejected, match="SOURCE_CHANGED_DURING_CAPTURE"):
            native.preserve_daily_rv(
                source,
                bronze,
                source_label="fixture",
                expected_snapshot_id=pin,
                imported_at=AT,
                actor_id="synthetic",
                code_revision=REVISION,
            )
        table = native.name(bronze, "bronze", "event_variants")
        assert bronze.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)
    finally:
        bronze.close()
        source.close()


def test_final_audit_failure_blocks_read_and_retry(tmp_path: Path, monkeypatch: Any) -> None:
    path = tmp_path / "legacy.duckdb"
    _source(path)
    source = duckdb.connect(str(path), read_only=True)
    bronze = _target(tmp_path / "bronze.duckdb")
    actual = AuditLedger.transition

    def fail(self: Any, job: str, state: JobState, reason_code: str | None = None) -> None:
        if state == JobState.SUCCEEDED:
            raise RuntimeError("INJECTED_FINAL_AUDIT_FAILURE")
        actual(self, job, state, reason_code)

    try:
        pin = native.capture_daily_rv(source, source_label="fixture").snapshot_id
        monkeypatch.setattr(AuditLedger, "transition", fail)
        with pytest.raises(RuntimeError, match="INJECTED_FINAL_AUDIT_FAILURE"):
            native.preserve_daily_rv(
                source,
                bronze,
                source_label="fixture",
                expected_snapshot_id=pin,
                imported_at=AT,
                actor_id="synthetic",
                code_revision=REVISION,
            )
        with pytest.raises(codec.Rejected, match="FIRST_WRITE_ORIGINAL_OBLIGATION"):
            native.preserve_daily_rv(
                source,
                bronze,
                source_label="fixture",
                expected_snapshot_id=pin,
                imported_at=AT,
                actor_id="synthetic",
                code_revision=REVISION,
            )
        event_table = native.name(bronze, "bronze", "event_variants")
        event = bronze.execute(
            f"SELECT capture_event_id,envelope_hash FROM {event_table}"
        ).fetchone()
        assert event is not None
    finally:
        bronze.close()
        source.close()
    reader = duckdb.connect(str(tmp_path / "bronze.duckdb"), read_only=True)
    try:
        with pytest.raises(codec.Rejected, match="ORIGINAL_AUDIT_NOT_VERIFIED"):
            native.read_daily_rv_bronze(
                reader,
                source_label="fixture",
                snapshot_id=pin,
                capture_event_id=event[0],
                envelope_hash=event[1],
                expected_recording_fingerprint="b" * 64,
            )
    finally:
        reader.close()


@pytest.mark.parametrize("rows", [0, 1001], ids=["empty", "overflow"])
def test_whole_table_not_partial(tmp_path: Path, rows: int) -> None:
    path = tmp_path / "legacy.duckdb"
    _source(path, rows=rows)
    source = duckdb.connect(str(path), read_only=True)
    try:
        with pytest.raises(codec.Rejected, match="WHOLE_TABLE_ROW_BOUND"):
            native.capture_daily_rv(source, source_label="fixture")
    finally:
        source.close()


def test_writable_source_rejected(tmp_path: Path) -> None:
    path = tmp_path / "legacy.duckdb"
    _source(path)
    source = duckdb.connect(str(path))
    try:
        with pytest.raises(codec.Rejected, match="READONLY_SOURCE_REQUIRED"):
            native.capture_daily_rv(source, source_label="fixture")
    finally:
        source.close()


def test_same_file_cursor_alias_keeps_parent(tmp_path: Path) -> None:
    parent = _target(tmp_path / "bronze.duckdb")
    alias = parent.cursor()
    try:
        with pytest.raises(codec.Rejected, match="SEPARATE_TARGET_REQUIRED"):
            native.preserve_daily_rv(
                alias,
                parent,
                source_label="fixture",
                expected_snapshot_id="a" * 64,
                imported_at=AT,
                actor_id="synthetic",
                code_revision=REVISION,
            )
        assert parent.execute("SELECT 1").fetchone() == (1,)
    finally:
        alias.close()
        parent.close()


def test_clock_normalization_and_naive_rejection() -> None:
    local = AT.astimezone(timezone(timedelta(hours=5, minutes=30)))
    assert native._clock(local) == native._clock(AT)
    with pytest.raises(codec.Rejected, match="AWARE_IMPORT_CLOCK_REQUIRED"):
        native._clock(datetime(2026, 1, 1))


@pytest.mark.parametrize("symbol", ["x" * 65536, "x" * 65537], ids=["text-limit", "text-overflow"])
def test_sql_text_bound(tmp_path: Path, symbol: str) -> None:
    path = tmp_path / "legacy.duckdb"
    _source(path, rows=1)
    writer = duckdb.connect(str(path))
    try:
        writer.execute(f"UPDATE {native.name(writer, 'main', codec.TABLE)} SET symbol=?", [symbol])
    finally:
        writer.close()
    source = duckdb.connect(str(path), read_only=True)
    try:
        if len(symbol) > codec.MAX_CELL:
            with pytest.raises(codec.Rejected, match="TEXT_TRANSFER_BOUND"):
                native.capture_daily_rv(source, source_label="fixture")
        else:
            assert native.capture_daily_rv(source, source_label="fixture").row_count == 1
    finally:
        source.close()


def test_native_batch_sql_failure_rolls_back_domain(tmp_path: Path) -> None:
    path = tmp_path / "legacy.duckdb"
    _source(path)
    source = duckdb.connect(str(path), read_only=True)
    owner = _target(tmp_path / "bronze.duckdb")

    class FailingConnection:
        def execute(self, sql: str, parameters: Any = None) -> Any:
            if sql.lstrip().startswith("INSERT INTO") and '"event_variants"' in sql:
                raise RuntimeError("INJECTED_VARIANT_INSERT_FAILURE")
            return owner.execute(sql) if parameters is None else owner.execute(sql, parameters)

    try:
        pin = native.capture_daily_rv(source, source_label="fixture").snapshot_id
        with pytest.raises(RuntimeError, match="INJECTED_VARIANT_INSERT_FAILURE"):
            native.preserve_daily_rv(
                source,
                FailingConnection(),
                source_label="fixture",
                expected_snapshot_id=pin,
                imported_at=AT,
                actor_id="synthetic",
                code_revision=REVISION,
            )
        for table in ("event_variants", "input_artifacts", "ingest_batches"):
            qualified = native.name(owner, "bronze", table)
            assert owner.execute(f"SELECT count(*) FROM {qualified}").fetchone() == (0,)
        events = native.name(owner, "medallion_audit", "job_events")
        assert owner.execute(f"SELECT state FROM {events} WHERE event_index=3").fetchone() == (
            "FAILED",
        )
    finally:
        owner.close()
        source.close()


@pytest.mark.parametrize(
    "kind",
    ["view", "wrong-type", "duplicate", "null", "nonfinite"],
    ids=["view", "wrong-type", "duplicate-key", "null-cell", "nan"],
)
def test_source_schema_and_rows_fail_closed(tmp_path: Path, kind: str) -> None:
    path = tmp_path / "legacy.duckdb"
    writer = duckdb.connect(str(path))
    table = native.name(writer, "main", codec.TABLE)
    try:
        if kind == "view":
            writer.execute(
                f"CREATE VIEW {table} AS SELECT 'N'::VARCHAR AS symbol,"
                "DATE '2026-01-01' AS trading_date,0.2::DOUBLE AS rv,"
                "2::BIGINT AS observation_count"
            )
        else:
            rv_type = "FLOAT" if kind == "wrong-type" else "DOUBLE"
            writer.execute(
                f"CREATE TABLE {table} (symbol VARCHAR,trading_date DATE,"
                f"rv {rv_type},observation_count BIGINT)"
            )
            writer.execute(f"INSERT INTO {table} VALUES ('N',DATE '2026-01-01',0.2,2)")
            if kind == "duplicate":
                writer.execute(f"INSERT INTO {table} SELECT * FROM {table}")
            elif kind == "null":
                writer.execute(f"UPDATE {table} SET rv=NULL")
            elif kind == "nonfinite":
                writer.execute(f"UPDATE {table} SET rv='NaN'::DOUBLE")
    finally:
        writer.close()
    source = duckdb.connect(str(path), read_only=True)
    try:
        with pytest.raises(codec.Rejected):
            native.capture_daily_rv(source, source_label="fixture")
        # A rejected capture rolls back its transaction and leaves the handle usable.
        assert source.execute("SELECT 1").fetchone() == (1,)
    finally:
        source.close()


def test_original_variant_orphan_blocks_capture(tmp_path: Path) -> None:
    legacy, target, receipt = _record(tmp_path)
    writer = duckdb.connect(str(target))
    try:
        for table in ("job_events", "jobs"):
            writer.execute(f"DELETE FROM {native.name(writer, 'medallion_audit', table)}")
    finally:
        writer.close()
    source = duckdb.connect(str(legacy), read_only=True)
    bronze = duckdb.connect(str(target))
    try:
        with pytest.raises(codec.Rejected, match="FIRST_WRITE_ORIGINAL_OBLIGATION"):
            native.preserve_daily_rv(
                source,
                bronze,
                source_label="fixture",
                expected_snapshot_id=receipt["snapshot_id"],
                imported_at=AT,
                actor_id="synthetic",
                code_revision=REVISION,
            )
    finally:
        bronze.close()
        source.close()
