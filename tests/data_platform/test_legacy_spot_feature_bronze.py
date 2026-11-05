"""Actual synthetic legacy builder/writer -> native spot-feature Bronze integration."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import duckdb
import pytest

from nse_quant.data_platform import legacy_daily_rv_bronze as common
from nse_quant.data_platform import legacy_spot_feature_bronze as native
from nse_quant.data_platform import legacy_spot_features as codec
from nse_quant.data_platform.audit import AuditLedger, JobState
from nse_quant.data_platform.bronze import BronzeEventStore
from nse_quant.features.spot_features import SpotFeatureBuilder
from nse_quant.persistence.duckdb_store import DuckDBStore

AT = datetime(2026, 1, 1, tzinfo=UTC)
REVISION = "a" * 40


def _source(path: Path) -> None:
    legacy = DuckDBStore(path=path)
    try:
        candles = [
            dict(
                date=AT + timedelta(minutes=i),
                open=100.0 + i,
                high=102.0 + i,
                low=99.0 + i,
                close=101.0 + i,
                volume=100 + i,
                oi=0,
            )
            for i in range(40)
        ]
        assert legacy.write_spot_candles(candles, "NIFTY", 256265, "1m") == 40
        frame = SpotFeatureBuilder(legacy).build("NIFTY")
        assert len(frame) == 40
        assert legacy.write_spot_features(frame) == 40
        replacement = frame.iloc[:1].copy()
        # Boundary value submitted through actual writer, not a recomputed builder close.
        replacement["close"] = -0.0
        assert legacy.write_spot_features(replacement) == 1
    finally:
        legacy.close()


def _record(tmp_path: Path) -> tuple[Path, Path, dict[str, Any]]:
    legacy_path = tmp_path / "legacy.duckdb"
    bronze_path = tmp_path / "bronze.duckdb"
    _source(legacy_path)
    source = duckdb.connect(str(legacy_path), read_only=True)
    target = duckdb.connect(str(bronze_path))
    try:
        AuditLedger(target).initialize()
        BronzeEventStore(target).initialize()
        snapshot = native.capture_spot_features(source, source_label="fixture")
        receipt = native.preserve_spot_features(
            source,
            target,
            source_label="fixture",
            expected_snapshot_id=snapshot.snapshot_id,
            imported_at=AT,
            actor_id="synthetic",
            code_revision=REVISION,
        )
    finally:
        target.close()
        source.close()
    return legacy_path, bronze_path, receipt


def _args(receipt: dict[str, Any]) -> dict[str, str]:
    return dict(
        source_label=receipt["source_label"],
        snapshot_id=receipt["snapshot_id"],
        capture_event_id=receipt["capture_event_id"],
        envelope_hash=receipt["envelope_hash"],
        expected_recording_fingerprint=receipt["recording_fingerprint"],
    )


def test_actual_builder_writer_native_producer_reader(tmp_path: Path) -> None:
    legacy_path, bronze_path, receipt = _record(tmp_path)
    source = duckdb.connect(str(legacy_path), read_only=True)
    bronze = duckdb.connect(str(bronze_path), read_only=True)
    try:
        records = native.read_spot_feature_bronze(bronze, **_args(receipt))
        assert records == native.revalidate_spot_feature_source(source, bronze, **_args(receipt))
        assert len(records) == 40  # replacement did not add a new stored key
        table = common.name(source, "main", codec.TABLE)
        columns = ",".join('"' + n + '"' for n in codec.NAMES)
        original = source.execute(f"SELECT {columns} FROM {table} ORDER BY ts").fetchall()
        for ordinal, (row, raw) in enumerate(zip(original, records, strict=True)):
            doc = codec.parse(raw, codec.MAX_RECORD)
            encoded = [
                codec.encode_cell(v, kind)
                for v, (_name, kind) in zip(row, codec.SCHEMA, strict=True)
            ]
            assert doc["source_ordinal"] == ordinal
            assert doc["stored_fields"] == dict(zip(codec.NAMES, encoded, strict=True))
            assert doc["native_features_recomputed"] is False
            assert doc["analytical_assumptions_verified"] is False
            assert doc["authoritative_market_coverage_verified"] is False
            assert doc["original_availability_at"] is None
            assert doc["decision_eligibility_asserted"] is False
        first = codec.parse(records[0], codec.MAX_RECORD)
        assert first["stored_fields"]["close"] == (-0.0).hex()
        assert first["stored_fields"]["return_1m"] is None
        assert first["stored_fields"]["rv_1m_30"] is None
        assert all(
            codec.parse(r, codec.MAX_RECORD)["stored_fields"]["trend_60m"] is None for r in records
        )
    finally:
        bronze.close()
        source.close()


def test_current_sql_change_separate_from_original_native_replay(tmp_path: Path) -> None:
    legacy_path, bronze_path, receipt = _record(tmp_path)
    writer = duckdb.connect(str(legacy_path))
    try:
        writer.execute(f"UPDATE {common.name(writer, 'main', codec.TABLE)} SET return_1m=0.5")
    finally:
        writer.close()
    source = duckdb.connect(str(legacy_path), read_only=True)
    bronze = duckdb.connect(str(bronze_path), read_only=True)
    try:
        assert len(native.read_spot_feature_bronze(bronze, **_args(receipt))) == 40
        with pytest.raises(codec.Rejected, match="CURRENT_LEGACY_SPOT_SOURCE_CHANGED"):
            native.revalidate_spot_feature_source(source, bronze, **_args(receipt))
    finally:
        bronze.close()
        source.close()


def test_failed_review_cannot_heal(tmp_path: Path) -> None:
    path = tmp_path / "legacy.duckdb"
    _source(path)
    source = duckdb.connect(str(path), read_only=True)
    target = duckdb.connect(str(tmp_path / "bronze.duckdb"))
    try:
        AuditLedger(target).initialize()
        BronzeEventStore(target).initialize()
        with pytest.raises(codec.Rejected, match="REVIEWED_SOURCE_CHANGED"):
            native.preserve_spot_features(
                source,
                target,
                source_label="fixture",
                expected_snapshot_id="b" * 64,
                imported_at=AT,
                actor_id="synthetic",
                code_revision=REVISION,
            )
        pin = native.capture_spot_features(source, source_label="fixture").snapshot_id
        with pytest.raises(codec.Rejected, match="FIRST_WRITE_ORIGINAL_OBLIGATION"):
            native.preserve_spot_features(
                source,
                target,
                source_label="fixture",
                expected_snapshot_id=pin,
                imported_at=AT,
                actor_id="other",
                code_revision="c" * 40,
            )
    finally:
        target.close()
        source.close()


@pytest.mark.parametrize(
    "kind",
    ["id", "envelope", "payload", "artifact", "audit", "clock"],
    ids=["event-id", "envelope-id", "payload", "artifact", "audit", "clock"],
)
def test_original_recording_tampering(tmp_path: Path, kind: str) -> None:
    _legacy_path, path, receipt = _record(tmp_path)
    writer = duckdb.connect(str(path))
    try:
        variants = common.name(writer, "bronze", "event_variants")
        if kind == "id":
            writer.execute(f"UPDATE {variants} SET capture_event_id=?", ["f" * 64])
        elif kind == "envelope":
            writer.execute(f"UPDATE {variants} SET envelope_hash=?", ["f" * 64])
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
            native.read_spot_feature_bronze(reader, **_args(receipt))
    finally:
        reader.close()


@pytest.mark.parametrize(
    "kind",
    ["view", "naive", "null-key", "duplicate", "nan", "overflow"],
    ids=["view", "naive-schema", "null-key", "duplicate-key", "nan", "rows"],
)
def test_schema_and_whole_table_limits(tmp_path: Path, kind: str) -> None:
    path = tmp_path / "legacy.duckdb"
    writer = duckdb.connect(str(path))
    try:
        table = common.name(writer, "main", codec.TABLE)
        if kind == "view":
            writer.execute(f"CREATE VIEW {table} AS SELECT 1 AS wrong")
        else:
            columns = ",".join(
                f'"{n}" {"TIMESTAMP" if n == "ts" and kind == "naive" else k}'
                for n, k in codec.SCHEMA
            )
            writer.execute(f"CREATE TABLE {table} ({columns})")
            writer.execute(
                f"INSERT INTO {table} (symbol,ts) VALUES (?,?)",
                [None if kind == "null-key" else "N", AT],
            )
            if kind == "duplicate":
                writer.execute(f"INSERT INTO {table} SELECT * FROM {table}")
            elif kind == "nan":
                writer.execute(f"UPDATE {table} SET close='NaN'::DOUBLE")
            elif kind == "overflow":
                writer.execute(
                    f"INSERT INTO {table} SELECT t.* FROM {table} t CROSS JOIN range(1000)"
                )
    finally:
        writer.close()
    reader = duckdb.connect(str(path), read_only=True)
    try:
        with pytest.raises(codec.Rejected):
            native.capture_spot_features(reader, source_label="fixture")
        assert reader.execute("SELECT 1").fetchone() == (1,)
    finally:
        reader.close()


@pytest.mark.parametrize("text", ["x" * 65536, "x" * 65537], ids=["text-limit", "text-overflow"])
def test_symbol_limit_has_short_pytest_id(tmp_path: Path, text: str) -> None:
    path = tmp_path / "legacy.duckdb"
    writer = duckdb.connect(str(path))
    try:
        table = common.name(writer, "main", codec.TABLE)
        columns = ",".join(f'"{n}" {k}' for n, k in codec.SCHEMA)
        writer.execute(f"CREATE TABLE {table} ({columns})")
        writer.execute(f"INSERT INTO {table} (symbol,ts) VALUES (?,?)", [text, AT])
    finally:
        writer.close()
    reader = duckdb.connect(str(path), read_only=True)
    try:
        if len(text) > codec.MAX_CELL:
            with pytest.raises(codec.Rejected, match="TEXT_TRANSFER_BOUND"):
                native.capture_spot_features(reader, source_label="fixture")
        else:
            assert native.capture_spot_features(reader, source_label="fixture").row_count == 1
    finally:
        reader.close()


def test_partial_native_batch_failure_rolls_back(tmp_path: Path) -> None:
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
        pin = native.capture_spot_features(source, source_label="fixture").snapshot_id
        with pytest.raises(RuntimeError, match="INJECTED_VARIANT_SQL_FAILURE"):
            native.preserve_spot_features(
                source,
                Fail(),
                source_label="fixture",
                expected_snapshot_id=pin,
                imported_at=AT,
                actor_id="synthetic",
                code_revision=REVISION,
            )
        for table in ("event_variants", "input_artifacts", "ingest_batches"):
            qualified = common.name(owner, "bronze", table)
            assert owner.execute(f"SELECT count(*) FROM {qualified}").fetchone() == (0,)
        events = common.name(owner, "medallion_audit", "job_events")
        assert owner.execute(f"SELECT state FROM {events} WHERE event_index=3").fetchone() == (
            "FAILED",
        )
    finally:
        owner.close()
        source.close()


def test_final_audit_failure_blocks_original(tmp_path: Path, monkeypatch: Any) -> None:
    path = tmp_path / "legacy.duckdb"
    _source(path)
    source = duckdb.connect(str(path), read_only=True)
    target_path = tmp_path / "bronze.duckdb"
    target = duckdb.connect(str(target_path))
    original = AuditLedger.transition

    def fail(self: Any, job: str, state: JobState, reason_code: str | None = None) -> None:
        if state == JobState.SUCCEEDED:
            raise RuntimeError("INJECTED_FINAL_AUDIT_FAILURE")
        original(self, job, state, reason_code)

    try:
        AuditLedger(target).initialize()
        BronzeEventStore(target).initialize()
        pin = native.capture_spot_features(source, source_label="fixture").snapshot_id
        monkeypatch.setattr(AuditLedger, "transition", fail)
        with pytest.raises(RuntimeError, match="INJECTED_FINAL_AUDIT_FAILURE"):
            native.preserve_spot_features(
                source,
                target,
                source_label="fixture",
                expected_snapshot_id=pin,
                imported_at=AT,
                actor_id="synthetic",
                code_revision=REVISION,
            )
        table = common.name(target, "bronze", "event_variants")
        row = target.execute(f"SELECT capture_event_id,envelope_hash FROM {table}").fetchone()
        assert row is not None
        with pytest.raises(codec.Rejected, match="FIRST_WRITE_ORIGINAL_OBLIGATION"):
            native.preserve_spot_features(
                source,
                target,
                source_label="fixture",
                expected_snapshot_id=pin,
                imported_at=AT,
                actor_id="other",
                code_revision=REVISION,
            )
    finally:
        target.close()
        source.close()
    reader = duckdb.connect(str(target_path), read_only=True)
    try:
        with pytest.raises(codec.Rejected, match="ORIGINAL_SPOT_AUDIT_NOT_VERIFIED"):
            native.read_spot_feature_bronze(
                reader,
                source_label="fixture",
                snapshot_id=pin,
                capture_event_id=row[0],
                envelope_hash=row[1],
                expected_recording_fingerprint="b" * 64,
            )
    finally:
        reader.close()


def test_alias_and_naive_clock_reject_without_parent_close(tmp_path: Path) -> None:
    owner = duckdb.connect(str(tmp_path / "bronze.duckdb"))
    alias = owner.cursor()
    try:
        AuditLedger(owner).initialize()
        BronzeEventStore(owner).initialize()
        with pytest.raises(codec.Rejected, match="SEPARATE_TARGET_REQUIRED"):
            native.preserve_spot_features(
                alias,
                owner,
                source_label="fixture",
                expected_snapshot_id="a" * 64,
                imported_at=AT,
                actor_id="synthetic",
                code_revision=REVISION,
            )
        assert owner.execute("SELECT 1").fetchone() == (1,)
    finally:
        alias.close()
        owner.close()
    row = ["N", datetime(2026, 1, 1).isoformat(), *([None] * 13)]
    with pytest.raises(codec.Rejected):
        codec.make_snapshot("fixture", [row])
    local = AT.astimezone(timezone(timedelta(hours=5, minutes=30)))
    assert codec.encode_cell(local, "TIMESTAMP WITH TIME ZONE") == AT.isoformat()


def test_second_actual_capture_then_injected_drift(tmp_path: Path, monkeypatch: Any) -> None:
    path = tmp_path / "legacy.duckdb"
    _source(path)
    source = duckdb.connect(str(path), read_only=True)
    target = duckdb.connect(str(tmp_path / "bronze.duckdb"))
    actual = native.capture_spot_features
    count = 0

    def drift(conn: Any, *, source_label: str) -> codec.Snapshot:
        nonlocal count
        value = actual(conn, source_label=source_label)
        count += 1
        if count == 2:
            # Boundary injection AFTER actual SQL capture, not authentic source drift.
            doc = codec.parse(value.payload, codec.MAX_BYTES)
            doc["rows"][0][2] = (9.5).hex()
            return codec.make_snapshot(source_label, doc["rows"])
        return value

    try:
        AuditLedger(target).initialize()
        BronzeEventStore(target).initialize()
        pin = actual(source, source_label="fixture").snapshot_id
        monkeypatch.setattr(native, "capture_spot_features", drift)
        with pytest.raises(codec.Rejected, match="SOURCE_CHANGED_DURING_CAPTURE"):
            native.preserve_spot_features(
                source,
                target,
                source_label="fixture",
                expected_snapshot_id=pin,
                imported_at=AT,
                actor_id="synthetic",
                code_revision=REVISION,
            )
    finally:
        target.close()
        source.close()


def test_strict_outer_json_and_duplicate_key() -> None:
    row = ["N", AT.isoformat(), *([None] * 13)]
    with pytest.raises(codec.Rejected, match="DUPLICATE_STORED_SPOT_KEY"):
        codec.make_snapshot("fixture", [row, row])
    snapshot = codec.make_snapshot("fixture", [row])
    doc = codec.parse(snapshot.payload, codec.MAX_BYTES)
    doc["unknown"] = True
    changed = codec.canonical(doc)
    with pytest.raises(codec.Rejected, match="COMPLETE_SPOT_FEATURE_REPLAY_MISMATCH"):
        codec.replay_snapshot(changed, expected_snapshot_id=codec.sha(changed))
    duplicate = b'{"version":1,"version":2}'
    with pytest.raises(codec.Rejected, match="DUPLICATE_JSON_KEY"):
        codec.replay_snapshot(duplicate, expected_snapshot_id=codec.sha(duplicate))


def test_canonical_snapshot_bound_is_independent_of_raw_text(tmp_path: Path) -> None:
    path = tmp_path / "legacy.duckdb"
    writer = duckdb.connect(str(path))
    try:
        table = common.name(writer, "main", codec.TABLE)
        columns = ",".join(f'"{n}" {k}' for n, k in codec.SCHEMA)
        writer.execute(f"CREATE TABLE {table} ({columns})")
        writer.executemany(
            f"INSERT INTO {table} (symbol,ts) VALUES (?,?)",
            [("x" * 65536, AT + timedelta(minutes=i)) for i in range(16)],
        )
    finally:
        writer.close()
    reader = duckdb.connect(str(path), read_only=True)
    try:
        with pytest.raises(codec.Rejected, match="SNAPSHOT_BYTE_BOUND"):
            native.capture_spot_features(reader, source_label="fixture")
    finally:
        reader.close()


def test_original_orphan_data_blocks_adoption(tmp_path: Path) -> None:
    legacy_path, bronze_path, receipt = _record(tmp_path)
    writer = duckdb.connect(str(bronze_path))
    try:
        for table in ("job_events", "jobs"):
            writer.execute(f"DELETE FROM {common.name(writer, 'medallion_audit', table)}")
    finally:
        writer.close()
    source = duckdb.connect(str(legacy_path), read_only=True)
    target = duckdb.connect(str(bronze_path))
    try:
        with pytest.raises(codec.Rejected, match="FIRST_WRITE_ORIGINAL_OBLIGATION"):
            native.preserve_spot_features(
                source,
                target,
                source_label="fixture",
                expected_snapshot_id=receipt["snapshot_id"],
                imported_at=AT,
                actor_id="synthetic",
                code_revision=REVISION,
            )
    finally:
        target.close()
        source.close()


def test_writable_source_refuses(tmp_path: Path) -> None:
    path = tmp_path / "legacy.duckdb"
    _source(path)
    writer = duckdb.connect(str(path))
    try:
        with pytest.raises(codec.Rejected, match="READONLY_SOURCE_REQUIRED"):
            native.capture_spot_features(writer, source_label="fixture")
    finally:
        writer.close()
